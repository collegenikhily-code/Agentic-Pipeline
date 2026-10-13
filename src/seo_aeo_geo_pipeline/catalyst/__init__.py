"""CATALYST orchestrator - central pipeline coordinator.

Manages PageJob lifecycle, bounded concurrency, failure isolation, and retries.
"""

from .orchestrator import Catalyst, JobResult, BatchResult
from .adapters import create_research_fn
