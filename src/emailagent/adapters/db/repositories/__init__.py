from .account import AccountRepository
from .analysis import AnalysisRepository
from .base import BaseRepository
from .email import EmailSyncRepository
from .search import SearchRepository


class EmailRepository(
    AccountRepository,
    EmailSyncRepository,
    AnalysisRepository,
    SearchRepository
):
    pass


__all__ = [
    "BaseRepository",
    "AccountRepository",
    "EmailSyncRepository",
    "AnalysisRepository",
    "SearchRepository",
    "EmailRepository"
]
