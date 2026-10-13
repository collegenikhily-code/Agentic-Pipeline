"""Discovery layer for keyword and competitor research.

Produces PageOpportunity objects from SE Ranking data.
"""

from .models import CompetitorPage, KeywordCluster, KeywordObservation, PageOpportunity
from .se_ranking import SERankingClient, SERankingError

__all__ = [
    "KeywordObservation",
    "CompetitorPage",
    "KeywordCluster",
    "PageOpportunity",
    "SERankingClient",
    "SERankingError",
]
