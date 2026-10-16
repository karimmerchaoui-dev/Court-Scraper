from enum import Enum, auto


class SearchResult(Enum):
    """Result codes for case search operations."""
    SUCCESS = auto()
    RETRY_NEEDED = auto()
    NOT_FOUND = auto()
    ERROR = auto()
