#!/usr/bin/env python3
"""
Simplified scraper using the RSS-first UnifiedScraper.

Usage:
    python scripts/run_unified.py                    # Scrape all sources
    python scripts/run_unified.py --source langchain # Scrape specific source
    python scripts/run_unified.py --list             # List available sources
    python scripts/run_unified.py --rss-only         # Only RSS sources (most reliable)
    python scripts/run_unified.py --dry-run          # Test without uploading
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import settings
from src.scrapers import HTML_ONLY_SOURCES, RSS_FEEDS, UnifiedScraper, list_sources
from src.storage import ContextualUploader, LocalStorage
from src.utils import ScrapeMetrics, setup_logging


def main():
    parser = argparse.ArgumentParser(
        description="RSS-first blog scraper for Context Crew",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_unified.py --list              # See all sources
  python scripts/run_unified.py --rss-only          # Most reliable sources only
  python scripts/run_unified.py --source langchain  # Single source
  python scripts/run_unified.py --dry-run           # Test without upload
        """,
    )

    parser.add_argument("--list", action="store_true", help="List all available sources")
    parser.add_argument("--source", type=str, help="Scrape a specific source")
    parser.add_argument(
        "--rss-only", action="store_true", help="Only scrape RSS sources (more reliable)"
    )
    parser.add_argument("--html-only", action="store_true", help="Only scrape HTML sources")
    parser.add_argument("--dry-run", action="store_true", help="Skip upload to Contextual AI")
    parser.add_argument("--max-articles", type=int, default=50, help="Max articles per source")
    parser.add_argument(
        "--force-rescrape",
        action="store_true",
        help="Ignore previously scraped articles and re-scrape everything",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        help="Only include articles published within this many days (default: 60)",
    )
    parser.add_argument("--output-dir", type=str, help="Override output directory")

    args = parser.parse_args()

    # Setup logging
    setup_logging()

    # List sources mode
    if args.list:
        list_sources()
        return

    # Determine which sources to scrape
    if args.source:
        all_sources = list(RSS_FEEDS.keys()) + list(HTML_ONLY_SOURCES.keys())
        if args.source not in all_sources:
            print(f"❌ Unknown source: {args.source}")
            print(f"   Available: {', '.join(all_sources)}")
            sys.exit(1)
        sources = [args.source]
    elif args.rss_only:
        sources = list(RSS_FEEDS.keys())
        print(f"📡 RSS-only mode: {len(sources)} sources")
    elif args.html_only:
        sources = list(HTML_ONLY_SOURCES.keys())
        print(f"🌐 HTML-only mode: {len(sources)} sources")
    else:
        sources = list(RSS_FEEDS.keys()) + list(HTML_ONLY_SOURCES.keys())
        print(f"📊 Scraping all {len(sources)} sources")

    # Initialize components
    scraper = UnifiedScraper(max_articles=args.max_articles, lookback_days=args.lookback_days)
    storage = LocalStorage(base_dir=Path(args.output_dir) if args.output_dir else None)
    metrics = ScrapeMetrics()

    # Load persistent URL registry (survives across CI runs)
    registry_path = (
        Path(args.output_dir).parent / "scraped_urls.json"
        if args.output_dir
        else Path("data/scraped_urls.json")
    )
    url_registry = storage.load_url_registry(registry_path)
    print(
        f"📋 Loaded URL registry: {sum(len(v) for v in url_registry.values())} total seen URLs across {len(url_registry)} sources"
    )

    # Initialize uploader (if not dry run)
    uploader = None
    if not args.dry_run and settings.contextual_api_key:
        uploader = ContextualUploader()
    elif args.dry_run:
        print("🧪 DRY RUN mode - uploads will be skipped")

    # Scrape each source
    all_articles = []

    for source_id in sources:
        print(f"\n{'='*60}")
        print(f"Scraping: {source_id}")
        print(f"{'='*60}")

        try:
            # Check for previously scraped URLs (deduplication via persistent registry)
            seen_urls = None
            if not args.force_rescrape:
                seen_urls = url_registry.get(source_id, set())
                if seen_urls:
                    print(f"  Found {len(seen_urls)} previously scraped articles")

            articles = scraper.scrape_source(source_id, seen_urls=seen_urls)

            if articles:
                # Get method used
                method = "RSS" if source_id in RSS_FEEDS else "HTML"
                print(f"  ✅ Scraped {len(articles)} new articles via {method}")

                # Save locally
                storage.save_batch(articles, source_id)
                metrics.record_scraped(source_id, len(articles))

                # Update persistent URL registry
                if source_id not in url_registry:
                    url_registry[source_id] = set()
                for article in articles:
                    if article.get("url"):
                        url_registry[source_id].add(article["url"])

                # Upload to Contextual AI
                if uploader:
                    results = uploader.upload_batch(articles)
                    metrics.record_uploaded(source_id, results["successful"])
                    if results["failed"] > 0:
                        print(f"  ⚠️  {results['failed']} uploads failed")

                all_articles.extend(articles)
            else:
                print("  ⚠️  No new articles found")
                metrics.record_skipped(source_id, 1)

        except Exception as e:
            print(f"  ❌ Error: {e}")
            metrics.record_error(source_id, "", str(e))

    # Print summary
    print("\n" + metrics.summary())

    # Save persistent URL registry
    if not args.dry_run:
        storage.save_url_registry(registry_path, url_registry)
        print(f"💾 URL registry saved to: {registry_path}")

    # Save report
    report_path = storage.base_dir / "scrape_report.json"
    with open(report_path, "w") as f:
        json.dump(metrics.to_dict(), f, indent=2)
    print(f"\n📄 Report saved to: {report_path}")

    # Final stats
    print(f"\n🎉 Done! Scraped {len(all_articles)} total articles")

    return 0 if metrics.to_dict()["total_errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
