#!/usr/bin/env python3
"""
Main entry point for the blog scraping pipeline.

Usage:
    python scripts/run_scraper.py --all              # Scrape all sources
    python scripts/run_scraper.py --source anthropic # Scrape specific source
    python scripts/run_scraper.py --all --dry-run    # Test without uploading
    python scripts/run_scraper.py --list-sources     # List available sources
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import settings
from src.scrapers import get_scraper
from src.storage import ContextualUploader, LocalStorage
from src.utils import ScrapeMetrics, get_logger, setup_logging


def load_sources_config() -> dict:
    """Load the sources configuration file."""
    config_path = settings.sources_config_path

    if not config_path.exists():
        # Try relative path
        config_path = project_root / "config" / "sources.yaml"

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    # Merge rss_sources and html_sources into a flat "sources" dict
    merged = {}
    merged.update(raw.get("rss_sources", {}))
    merged.update(raw.get("html_sources", {}))
    if merged:
        raw["sources"] = merged

    return raw


def get_enabled_sources(config: dict) -> list[tuple[str, dict]]:
    """Get list of enabled sources from config."""
    sources = []
    for source_id, source_config in config.get("sources", {}).items():
        if source_config.get("enabled", True):
            sources.append((source_id, source_config))

    # Sort by priority (lower = higher priority)
    sources.sort(key=lambda x: x[1].get("priority", 99))
    return sources


def run_scraper_for_source(
    source_id: str,
    source_config: dict,
    storage: LocalStorage,
    uploader: ContextualUploader | None,
    metrics: ScrapeMetrics,
    force_rescrape: bool = False,
) -> list[dict]:
    """Run scraper for a single source."""
    logger = get_logger("runner")

    logger.info(f"Starting scrape for: {source_config.get('name', source_id)}")

    # Get the scraper class
    scraper_class_name = source_config.get("scraper_class", "GenericScraper")

    try:
        scraper_class = get_scraper(scraper_class_name)
    except ValueError as e:
        logger.error(f"Unknown scraper class: {scraper_class_name}")
        metrics.record_error(source_id, "", str(e))
        return []

    # Instantiate scraper with config
    scraper_kwargs = {
        "max_articles": source_config.get("max_articles", settings.max_articles_per_source),
        "rate_limit_seconds": source_config.get(
            "rate_limit_seconds", settings.scrape_delay_seconds
        ),
    }

    # For generic scraper, pass additional config
    if scraper_class_name == "GenericScraper":
        scraper = scraper_class(
            source_name=source_config.get("name", source_id),
            base_url=source_config.get("base_url"),
            blog_path=source_config.get("blog_path", "/blog"),
            **scraper_kwargs,
        )
    else:
        scraper = scraper_class(**scraper_kwargs)

    # Get already-scraped URLs (for deduplication)
    if not force_rescrape:
        existing_urls = storage.get_scraped_urls(source_id)
        logger.info(f"Found {len(existing_urls)} existing URLs for {source_id}")
    else:
        existing_urls = set()

    # Run the scraper
    try:
        articles = scraper.scrape_all()
    except Exception as e:
        logger.error(f"Scraper failed for {source_id}: {str(e)}")
        metrics.record_error(source_id, "", str(e))
        return []

    # Filter out duplicates
    new_articles = []
    for article in articles:
        if article.get("url") not in existing_urls:
            new_articles.append(article)
        else:
            metrics.record_skipped(source_id)

    logger.info(f"Scraped {len(articles)} articles, {len(new_articles)} are new")
    metrics.record_scraped(source_id, len(new_articles))

    # Save to local storage
    if new_articles:
        storage.save_batch(new_articles, source_id)
        logger.info(f"Saved {len(new_articles)} articles to local storage")

    # Upload to Contextual AI
    if uploader and new_articles and not settings.skip_upload:
        upload_results = uploader.upload_batch(new_articles)
        metrics.record_uploaded(source_id, upload_results["successful"])

        for error in upload_results.get("errors", []):
            if isinstance(error, dict):
                metrics.record_error(source_id, error.get("url", ""), "Upload failed")

    return new_articles


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Blog scraping pipeline for Context Crew",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Scrape all enabled sources",
    )
    parser.add_argument(
        "--source",
        type=str,
        help="Scrape a specific source by ID",
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="List all available sources",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without uploading to Contextual AI",
    )
    parser.add_argument(
        "--force-rescrape",
        action="store_true",
        help="Rescrape even if URL was previously scraped",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Override local data directory",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        help="Override max articles per source",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging()
    logger = get_logger("main")

    # Load config
    try:
        config = load_sources_config()
    except FileNotFoundError:
        logger.error("Could not find sources.yaml config file")
        sys.exit(1)

    # List sources mode
    if args.list_sources:
        print("\nAvailable Sources:")
        print("-" * 60)
        for source_id, source_config in config.get("sources", {}).items():
            enabled = "✓" if source_config.get("enabled", True) else "✗"
            name = source_config.get("name", source_id)
            scraper = source_config.get("scraper_class", "GenericScraper")
            print(f"  [{enabled}] {source_id:15} - {name:25} ({scraper})")
        print()
        return

    # Validate arguments
    if not args.all and not args.source:
        parser.print_help()
        print("\nError: Must specify --all or --source")
        sys.exit(1)

    # Apply overrides
    if args.dry_run:
        settings.skip_upload = True
        logger.info("DRY RUN mode - uploads will be skipped")

    if args.max_articles:
        settings.max_articles_per_source = args.max_articles

    # Initialize storage
    output_dir = Path(args.output_dir) if args.output_dir else None
    storage = LocalStorage(base_dir=output_dir)

    # Initialize uploader (if not dry run)
    uploader = None
    if not settings.skip_upload and settings.contextual_api_key:
        uploader = ContextualUploader()

    # Initialize metrics
    metrics = ScrapeMetrics()

    # Determine which sources to scrape
    if args.source:
        source_config = config.get("sources", {}).get(args.source)
        if not source_config:
            logger.error(f"Unknown source: {args.source}")
            sys.exit(1)
        sources_to_scrape = [(args.source, source_config)]
    else:
        sources_to_scrape = get_enabled_sources(config)

    logger.info(f"Will scrape {len(sources_to_scrape)} sources")

    # Run scrapers
    all_articles = []
    for source_id, source_config in sources_to_scrape:
        try:
            articles = run_scraper_for_source(
                source_id=source_id,
                source_config=source_config,
                storage=storage,
                uploader=uploader,
                metrics=metrics,
                force_rescrape=args.force_rescrape or settings.force_rescrape,
            )
            all_articles.extend(articles)
        except Exception as e:
            logger.error(f"Error processing {source_id}: {str(e)}")
            metrics.record_error(source_id, "", str(e))

    # Print summary
    print(metrics.summary())

    # Save metrics report
    metrics_path = storage.base_dir / "scrape_report.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics.to_dict(), f, indent=2)
    logger.info(f"Saved metrics report to {metrics_path}")

    # Exit with error code if there were failures
    if metrics.to_dict()["total_errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
