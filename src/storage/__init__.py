"""Storage modules for scraped articles."""

from .local_storage import LocalStorage
from .contextual_uploader import ContextualUploader

__all__ = [
    "LocalStorage",
    "ContextualUploader",
]
