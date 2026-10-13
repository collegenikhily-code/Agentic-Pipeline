"""Tests for CATALYST concurrent research dispatch."""

import pytest
import time
from seo_aeo_geo_pipeline.catalyst.orchestrator import Catalyst, BatchResult
from seo_aeo_geo_pipeline.catalyst.adapters import create_research_fn
from seo_aeo_geo_pipeline.models import PageJob
from seo_aeo_geo_pipeline.research.agents.research_agent import ResearchAgent


class TestCatalystConcurrent:
    def _make_job(self, keyword: str, intent: str = "informational") -> PageJob:
        return PageJob(job_id=f"job-{keyword[:20]}", keyword=keyword, intent=intent)

    def test_catalyst_runs_multiple_jobs(self):
        """CATALYST should execute multiple jobs and report results."""
        agent = ResearchAgent()
        research_fn = create_research_fn(agent)

        catalyst = Catalyst(max_concurrency=2)
        catalyst.add_jobs([
            self._make_job("meta ads mcp"),
            self._make_job("ai blend tool"),
        ])

        batch = catalyst.run(research_fn)
        assert isinstance(batch, BatchResult)
        assert batch.total_jobs == 2
        assert batch.successful == 2
        assert batch.failed == 0

    def test_catalyst_failure_isolation(self):
        """One failing job must not terminate others."""
        call_count = {"n": 0}

        def research_fn(job: PageJob) -> dict:
            call_count["n"] += 1
            if "fail" in job.keyword.lower():
                raise ValueError("Intentional test failure")
            agent = ResearchAgent()
            return agent.run_full_cycle(keyword=job.keyword, intent=job.intent)

        catalyst = Catalyst(max_concurrency=2)
        catalyst.add_jobs([
            self._make_job("good keyword"),
            self._make_job("fail keyword"),
            self._make_job("another good keyword"),
        ])

        batch = catalyst.run(research_fn)
        assert batch.total_jobs == 3
        assert batch.successful == 2
        assert batch.failed == 1

        # Verify the failing job's error is captured
        failed_results = [r for r in batch.results if not r.success]
        assert len(failed_results) == 1
        assert "ValueError" in failed_results[0].error

    def test_catalyst_concurrent_execution_timing(self):
        """Concurrent execution should be faster than sequential."""
        def slow_research(job: PageJob) -> dict:
            time.sleep(0.05)  # Simulate some work
            agent = ResearchAgent()
            return agent.run_full_cycle(keyword=job.keyword, intent=job.intent)

        catalyst = Catalyst(max_concurrency=3)
        catalyst.add_jobs([
            self._make_job("keyword a"),
            self._make_job("keyword b"),
            self._make_job("keyword c"),
        ])

        start = time.time()
        batch = catalyst.run(slow_research)
        elapsed = time.time() - start

        assert batch.successful == 3
        # With concurrency=3, 3 jobs of 50ms should take ~50-100ms total, not 150ms
        assert elapsed < 0.3

    def test_catalyst_run_sync_mode(self):
        """Sync mode should also work."""
        agent = ResearchAgent()
        research_fn = create_research_fn(agent)

        catalyst = Catalyst(max_concurrency=2)
        catalyst.add_jobs([
            self._make_job("sync keyword"),
        ])

        batch = catalyst.run_sync(research_fn)
        assert batch.successful == 1

    def test_catalyst_batch_summary(self):
        """Batch summary should contain all expected fields."""
        agent = ResearchAgent()
        research_fn = create_research_fn(agent)

        catalyst = Catalyst(max_concurrency=2)
        catalyst.add_jobs([self._make_job("summary test")])

        batch = catalyst.run(research_fn)
        summary = batch.summary()
        assert "total_jobs" in summary
        assert "successful" in summary
        assert "failed" in summary
        assert "results" in summary
        assert summary["total_jobs"] == 1
