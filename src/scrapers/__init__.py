"""
Blog scrapers for various sources.

Uses the UnifiedScraper which:
- Uses RSS feeds when available (preferred, more reliable)
- Falls back to HTML scraping when needed
"""

from .unified_scraper import (
    FILTERING,
    GLOBAL_CONFIG,
    HTML_ONLY_SOURCES,
    RSS_FEEDS,
    UnifiedScraper,
    get_all_sources,
    list_sources,
    load_sources_config,
)

__all__ = [
    "UnifiedScraper",
    "RSS_FEEDS",
    "HTML_ONLY_SOURCES",
    "FILTERING",
    "GLOBAL_CONFIG",
    "load_sources_config",
    "get_all_sources",
    "list_sources",
]
