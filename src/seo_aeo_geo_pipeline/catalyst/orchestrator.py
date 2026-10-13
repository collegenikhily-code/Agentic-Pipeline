"""CATALYST Orchestrator - central pipeline coordinator.

Manages PageJob lifecycle, bounded concurrency, failure isolation, and retries.
Uses asyncio with semaphores for bounded concurrency. No external dependencies.

Architecture:
  CATALYST accepts PageJobs, dispatches independent jobs with bounded concurrency,
  isolates failures between jobs, tracks per-job state, and returns structured results.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from seo_aeo_geo_pipeline.models import PageJob

logger = logging.getLogger(__name__)


@dataclass
class JobResult:
    """Structured result for a single PageJob execution."""
    job_id: str
    success: bool
    research_result: Optional[dict] = None
    error: Optional[str] = None
    retries_used: int = 0


@dataclass
class BatchResult:
    """Structured result for a batch of PageJob executions."""
    results: list[JobResult] = field(default_factory=list)
    total_jobs: int = 0
    successful: int = 0
    failed: int = 0

    def summary(self) -> dict:
        return {
            "total_jobs": self.total_jobs,
            "successful": self.successful,
            "failed": self.failed,
            "results": [r.__dict__ for r in self.results],
        }


# Type alias for the research function a stage must provide
ResearchFn = Callable[[PageJob], dict]


class Catalyst:
    """CATALYST orchestrator - central pipeline coordinator.

    Usage:
        catalyst = Catalyst(max_concurrency=3)
        catalyst.add_jobs([
            PageJob(job_id="j1", keyword="best CRM", intent="commercial"),
            PageJob(job_id="j2", keyword="what is SEO", intent="informational"),
        ])
        result = catalyst.run(research_fn=my_research_function)
    """

    def __init__(self, max_concurrency: int = 3) -> None:
        self.max_concurrency = max_concurrency
        self._jobs: list[PageJob] = []
        self._results: list[JobResult] = []

    def add_job(self, job: PageJob) -> None:
        """Add a single PageJob to the queue."""
        self._jobs.append(job)

    def add_jobs(self, jobs: list[PageJob]) -> None:
        """Add multiple PageJobs to the queue."""
        self._jobs.extend(jobs)

    def clear(self) -> None:
        """Clear all queued jobs and results."""
        self._jobs.clear()
        self._results.clear()

    @property
    def jobs(self) -> list[PageJob]:
        """Read-only access to queued jobs."""
        return list(self._jobs)

    @property
    def results(self) -> list[JobResult]:
        """Read-only access to last run's results."""
        return list(self._results)

    def run(self, research_fn: ResearchFn) -> BatchResult:
        """Execute all queued jobs with bounded concurrency.

        Args:
            research_fn: Callable that takes a PageJob and returns a research result dict.
                        Must raise an exception on failure (do not return error dicts).

        Returns:
            BatchResult with per-job outcomes.
        """
        return asyncio.run(self._run_async(research_fn))

    async def _run_async(self, research_fn: ResearchFn) -> BatchResult:
        """Async execution engine with bounded concurrency."""
        semaphore = asyncio.Semaphore(self.max_concurrency)
        batch = BatchResult(total_jobs=len(self._jobs))

        async def _run_one(job: PageJob) -> JobResult:
            async with semaphore:
                return await self._execute_job(job, research_fn)

        tasks = [_run_one(job) for job in self._jobs]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        for r in results:
            batch.results.append(r)
            if r.success:
                batch.successful += 1
            else:
                batch.failed += 1

        self._results = batch.results
        return batch

    async def _execute_job(self, job: PageJob, research_fn: ResearchFn) -> JobResult:
        """Execute a single PageJob with failure isolation."""
        try:
            job.mark_researching()
            logger.info(f"CATALYST: Researching {job.job_id} ({job.keyword})")

            # Run the research function in a thread to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, research_fn, job)

            job.mark_researched(result)
            logger.info(f"CATALYST: Researched {job.job_id}")

            job.mark_completed()
            return JobResult(
                job_id=job.job_id,
                success=True,
                research_result=result,
                retries_used=job.retry_count,
            )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"CATALYST: Job {job.job_id} failed: {error_msg}")
            job.mark_failed(error_msg)

            # Auto-retry if possible
            if job.can_retry():
                logger.info(f"CATALYST: Retrying {job.job_id} (attempt {job.retry_count + 1})")
                job.retry()
                return await self._execute_job(job, research_fn)

            return JobResult(
                job_id=job.job_id,
                success=False,
                error=error_msg,
                retries_used=job.retry_count,
            )

    def run_sync(self, research_fn: ResearchFn) -> BatchResult:
        """Synchronous execution using thread pool (for non-async contexts).

        Identical semantics to run() but uses ThreadPoolExecutor instead of asyncio.
        """
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
            batch = BatchResult(total_jobs=len(self._jobs))

            def _execute(job: PageJob) -> JobResult:
                try:
                    job.mark_researching()
                    result = research_fn(job)
                    job.mark_researched(result)
                    job.mark_completed()
                    return JobResult(
                        job_id=job.job_id,
                        success=True,
                        research_result=result,
                        retries_used=job.retry_count,
                    )
                except Exception as e:
                    error_msg = f"{type(e).__name__}: {e}"
                    job.mark_failed(error_msg)

                    if job.can_retry():
                        job.retry()
                        return _execute(job)

                    return JobResult(
                        job_id=job.job_id,
                        success=False,
                        error=error_msg,
                        retries_used=job.retry_count,
                    )

            futures = {executor.submit(_execute, job): job for job in self._jobs}
            for future in futures:
                r = future.result()
                batch.results.append(r)
                if r.success:
                    batch.successful += 1
                else:
                    batch.failed += 1

            self._results = batch.results
            return batch
