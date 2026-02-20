"""Storage modules for scraped articles."""

from .contextual_uploader import ContextualUploader
from .local_storage import LocalStorage

__all__ = [
    "LocalStorage",
    "ContextualUploader",
]
