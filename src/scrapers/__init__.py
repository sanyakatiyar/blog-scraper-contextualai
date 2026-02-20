"""
Blog scrapers for various sources.

The recommended approach is to use the UnifiedScraper which:
- Uses RSS feeds when available (preferred, more reliable)
- Falls back to HTML scraping when needed

Individual scrapers are kept for backwards compatibility.
"""

from .anthropic_scraper import AnthropicScraper
from .base_scraper import BaseScraper
from .generic_scraper import GenericScraper
from .huggingface_scraper import HuggingFaceScraper
from .langchain_scraper import LangChainScraper
from .llamaindex_scraper import LlamaIndexScraper
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

# Registry of individual scrapers (legacy)
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "AnthropicScraper": AnthropicScraper,
    "LlamaIndexScraper": LlamaIndexScraper,
    "LangChainScraper": LangChainScraper,
    "HuggingFaceScraper": HuggingFaceScraper,
    "GenericScraper": GenericScraper,
}


def get_scraper(scraper_class: str) -> type[BaseScraper]:
    """Get a scraper class by name (legacy)."""
    if scraper_class not in SCRAPER_REGISTRY:
        raise ValueError(
            f"Unknown scraper: {scraper_class}. Available: {list(SCRAPER_REGISTRY.keys())}"
        )
    return SCRAPER_REGISTRY[scraper_class]


__all__ = [
    # Recommended
    "UnifiedScraper",
    "RSS_FEEDS",
    "HTML_ONLY_SOURCES",
    "FILTERING",
    "GLOBAL_CONFIG",
    "load_sources_config",
    "get_all_sources",
    "list_sources",
    # Legacy
    "BaseScraper",
    "AnthropicScraper",
    "LlamaIndexScraper",
    "LangChainScraper",
    "HuggingFaceScraper",
    "GenericScraper",
    "SCRAPER_REGISTRY",
    "get_scraper",
]
