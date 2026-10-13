"""CATALYST orchestrator + PageJob lifecycle tests.

No PostgreSQL required - tests PageJob state machine, CATALYST concurrency,
failure isolation, and retry logic.
"""

import pytest
import time
import threading
from seo_aeo_geo_pipeline.models import PageJob, pagejob_can_transition
from seo_aeo_geo_pipeline.catalyst import Catalyst, JobResult


# ── PageJob Lifecycle Tests ──────────────────────────────────────────────


class TestPageJobLifecycle:
    """PageJob state machine: QUEUED → RESEARCHING → RESEARCHED → COMPLETED."""

    def test_pagejob_creation(self):
        """PageJob can be created with required fields."""
        job = PageJob(job_id="j1", keyword="best CRM", intent="commercial")
        assert job.job_id == "j1"
        assert job.keyword == "best CRM"
        assert job.intent == "commercial"
        assert job.status == "QUEUED"
        assert job.research_result is None
        assert job.error is None
        assert job.retry_count == 0
        assert job.max_retries == 2

    def test_pagejob_valid_transitions(self):
        """PageJob follows QUEUED → RESEARCHING → RESEARCHED → COMPLETED."""
        job = PageJob(job_id="j1", keyword="test")
        assert job.status == "QUEUED"

        job.mark_researching()
        assert job.status == "RESEARCHING"

        job.mark_researched({"sources": []})
        assert job.status == "RESEARCHED"
        assert job.research_result == {"sources": []}

        job.mark_completed()
        assert job.status == "COMPLETED"
        assert job.is_terminal()

    def test_pagejob_invalid_transition_raises(self):
        """PageJob raises ValueError on invalid transition."""
        job = PageJob(job_id="j1", keyword="test")
        with pytest.raises(ValueError, match="Invalid PageJob transition"):
            job.transition("COMPLETED")  # QUEUED → COMPLETED is invalid

    def test_pagejob_failed_state(self):
        """PageJob can transition to FAILED from any non-terminal state."""
        job = PageJob(job_id="j1", keyword="test")
        job.mark_failed("research error")
        assert job.status == "FAILED"
        assert job.error == "research error"
        assert not job.is_terminal()

    def test_pagejob_retry(self):
        """FAILED PageJob can retry back to QUEUED."""
        job = PageJob(job_id="j1", keyword="test", max_retries=2)
        job.mark_failed("error 1")
        assert job.can_retry()

        job.retry()
        assert job.status == "QUEUED"
        assert job.retry_count == 1
        assert job.error is None

    def test_pagejob_retry_exhausted(self):
        """PageJob stops retrying after max_retries."""
        job = PageJob(job_id="j1", keyword="test", max_retries=1)
        job.mark_failed("error 1")
        job.retry()
        job.mark_failed("error 2")
        assert not job.can_retry()
        assert job.is_terminal()

    def test_pagejob_to_dict(self):
        """PageJob serializes to dictionary."""
        job = PageJob(job_id="j1", keyword="test", intent="informational")
        d = job.to_dict()
        assert d["job_id"] == "j1"
        assert d["keyword"] == "test"
        assert d["status"] == "QUEUED"
        assert "created_at" in d

    def test_pagejob_transition_function(self):
        """pagejob_can_transition correctly validates transitions."""
        assert pagejob_can_transition("QUEUED", "RESEARCHING") is True
        assert pagejob_can_transition("QUEUED", "FAILED") is True
        assert pagejob_can_transition("QUEUED", "COMPLETED") is False
        assert pagejob_can_transition("RESEARCHING", "RESEARCHED") is True
        assert pagejob_can_transition("RESEARCHING", "FAILED") is True
        assert pagejob_can_transition("RESEARCHED", "COMPLETED") is True
        assert pagejob_can_transition("COMPLETED", "QUEUED") is False
        assert pagejob_can_transition("FAILED", "QUEUED") is True


# ── CATALYST Orchestrator Tests ─────────────────────────────────────────


class TestCatalyst:
    """CATALYST orchestrator concurrency and failure isolation."""

    def test_catalyst_single_job(self):
        """CATALYST executes a single job successfully."""
        def research_fn(job):
            return {"keyword": job.keyword, "sources": []}

        catalyst = Catalyst(max_concurrency=1)
        catalyst.add_job(PageJob(job_id="j1", keyword="test keyword"))
        result = catalyst.run(research_fn)

        assert result.total_jobs == 1
        assert result.successful == 1
        assert result.failed == 0
        assert result.results[0].success is True
        assert result.results[0].research_result["keyword"] == "test keyword"

    def test_catalyst_parallel_execution(self):
        """CATALYST runs multiple jobs in parallel with bounded concurrency."""
        execution_times = []
        lock = threading.Lock()

        def research_fn(job):
            start = time.monotonic()
            time.sleep(0.05)  # simulate work
            end = time.monotonic()
            with lock:
                execution_times.append((job.job_id, start, end))
            return {"keyword": job.keyword}

        catalyst = Catalyst(max_concurrency=3)
        catalyst.add_jobs([
            PageJob(job_id="j1", keyword="keyword 1"),
            PageJob(job_id="j2", keyword="keyword 2"),
            PageJob(job_id="j3", keyword="keyword 3"),
        ])
        result = catalyst.run(research_fn)

        assert result.total_jobs == 3
        assert result.successful == 3
        assert result.failed == 0

        # Verify all jobs completed
        for r in result.results:
            assert r.success is True

    def test_catalyst_failure_isolation(self):
        """One job failure does not kill other jobs."""
        def research_fn(job):
            if job.job_id == "j2":
                raise ValueError("j2 research failed")
            return {"keyword": job.keyword}

        catalyst = Catalyst(max_concurrency=2)
        catalyst.add_jobs([
            PageJob(job_id="j1", keyword="keyword 1"),
            PageJob(job_id="j2", keyword="keyword 2"),
            PageJob(job_id="j3", keyword="keyword 3"),
        ])
        result = catalyst.run(research_fn)

        assert result.total_jobs == 3
        assert result.successful == 2
        assert result.failed == 1

        # j1 and j3 succeeded
        successes = {r.job_id: r for r in result.results if r.success}
        assert "j1" in successes
        assert "j3" in successes

        # j2 failed
        failures = {r.job_id: r for r in result.results if not r.success}
        assert "j2" in failures
        assert "j2 research failed" in failures["j2"].error

    def test_catalyst_retry_on_failure(self):
        """CATALYST automatically retries failed jobs."""
        attempt_count = {}

        def research_fn(job):
            key = job.job_id
            attempt_count[key] = attempt_count.get(key, 0) + 1
            if key == "j_fail" and attempt_count[key] < 2:
                raise RuntimeError("transient error")
            return {"keyword": job.keyword, "attempt": attempt_count[key]}

        catalyst = Catalyst(max_concurrency=1)
        catalyst.add_job(PageJob(job_id="j_fail", keyword="flaky", max_retries=2))
        result = catalyst.run(research_fn)

        assert result.successful == 1
        assert result.failed == 0
        assert attempt_count["j_fail"] == 2  # retried once

    def test_catalyst_retry_exhausted(self):
        """Job fails permanently after exhausting retries."""
        def research_fn(job):
            raise RuntimeError("persistent error")

        catalyst = Catalyst(max_concurrency=1)
        catalyst.add_job(PageJob(job_id="j_bad", keyword="bad", max_retries=1))
        result = catalyst.run(research_fn)

        assert result.successful == 0
        assert result.failed == 1
        assert result.results[0].retries_used == 1

    def test_catalyst_empty_batch(self):
        """CATALYST handles empty job list."""
        def research_fn(job):
            return {}

        catalyst = Catalyst(max_concurrency=3)
        result = catalyst.run(research_fn)

        assert result.total_jobs == 0
        assert result.successful == 0
        assert result.failed == 0
        assert result.results == []

    def test_catalyst_batch_summary(self):
        """BatchResult.summary() returns structured dict."""
        def research_fn(job):
            return {"ok": True}

        catalyst = Catalyst(max_concurrency=2)
        catalyst.add_jobs([
            PageJob(job_id="j1", keyword="a"),
            PageJob(job_id="j2", keyword="b"),
        ])
        result = catalyst.run(research_fn)
        summary = result.summary()

        assert summary["total_jobs"] == 2
        assert summary["successful"] == 2
        assert summary["failed"] == 0
        assert len(summary["results"]) == 2

    def test_catalyst_clear(self):
        """CATALYST clear resets jobs and results."""
        def research_fn(job):
            return {}

        catalyst = Catalyst(max_concurrency=1)
        catalyst.add_job(PageJob(job_id="j1", keyword="a"))
        catalyst.run(research_fn)
        assert len(catalyst.results) == 1

        catalyst.clear()
        assert len(catalyst.jobs) == 0
        assert len(catalyst.results) == 0

    def test_catalyst_sync_mode(self):
        """CATALYST run_sync works identically to run."""
        def research_fn(job):
            return {"keyword": job.keyword}

        catalyst = Catalyst(max_concurrency=2)
        catalyst.add_jobs([
            PageJob(job_id="j1", keyword="sync test 1"),
            PageJob(job_id="j2", keyword="sync test 2"),
        ])
        result = catalyst.run_sync(research_fn)

        assert result.total_jobs == 2
        assert result.successful == 2
        for r in result.results:
            assert r.success is True

    def test_catalyst_concurrency_bounded(self):
        """CATALYST respects max_concurrency limit."""
        active_count = {"value": 0}
        max_seen = {"value": 0}
        lock = threading.Lock()

        def research_fn(job):
            with lock:
                active_count["value"] += 1
                max_seen["value"] = max(max_seen["value"], active_count["value"])
            time.sleep(0.05)
            with lock:
                active_count["value"] -= 1
            return {"ok": True}

        catalyst = Catalyst(max_concurrency=2)
        catalyst.add_jobs([
            PageJob(job_id=f"j{i}", keyword=f"kw {i}") for i in range(5)
        ])
        result = catalyst.run(research_fn)

        assert result.total_jobs == 5
        assert result.successful == 5
        # Max concurrent should not exceed 2
        assert max_seen["value"] <= 2


# ── Integration: CATALYST + ResearchAgent wiring ─────────────────────────


class TestCatalystResearchIntegration:
    """Minimal integration test: CATALYST → ResearchAgent (no mocks)."""

    def test_catalyst_researches_real_job(self):
        """CATALYST executes a real PageJob through actual ResearchAgent."""
        from seo_aeo_geo_pipeline.research.agents import ResearchAgent
        from seo_aeo_geo_pipeline.catalyst import create_research_fn

        agent = ResearchAgent()
        research_fn = create_research_fn(agent)

        job = PageJob(
            job_id="int-test-001",
            keyword="best CRM for textile manufacturers",
            intent="commercial",
        )

        catalyst = Catalyst(max_concurrency=1)
        catalyst.add_job(job)
        batch = catalyst.run(research_fn)

        # Job succeeded
        assert batch.successful == 1
        assert batch.failed == 0
        assert batch.results[0].success is True

        # PageJob transitions completed
        assert job.status == "COMPLETED"
        assert job.is_terminal()

        # Research result contains plan, dataset, snapshot
        assert job.research_result is not None
        assert "plan" in job.research_result
        assert "dataset" in job.research_result
        assert "snapshot" in job.research_result

        # Snapshot has required fields
        snapshot = job.research_result["snapshot"]
        assert snapshot["primary_keyword"] == "best CRM for textile manufacturers"
        assert snapshot["intent"] == "commercial"
        assert snapshot["page_type_recommendation"] == "comparison-guide"
        assert "content_gaps" in snapshot
        assert "differentiation_strategy" in snapshot
