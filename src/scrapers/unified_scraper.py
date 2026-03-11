"""
Unified RSS-First Blog Scraper

This scraper prioritizes RSS feeds for reliability and only falls back
to HTML scraping when no RSS feed is available.

RSS feeds are:
- More stable (don't break when site redesigns)
- Structured (no CSS selector guessing)
- Polite (designed for automated access)
- Faster (smaller payload than full HTML)
"""

import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests
import trafilatura
import yaml
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from config.settings import settings
from src.utils import get_logger, rate_limiter

# =============================================================================
# Load sources and filtering config from YAML
# =============================================================================


def load_sources_config() -> tuple[dict, dict, dict, dict]:
    """
    Load RSS feeds, HTML sources, filtering rules, and global settings
    from config/sources.yaml.

    Returns:
        (rss_feeds, html_sources, filtering, global_config)
    """
    config_path = settings.sources_config_path
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    rss_feeds = {}
    for source_id, cfg in (raw.get("rss_sources") or {}).items():
        if not cfg.get("enabled", True):
            continue
        rss_feeds[source_id] = {
            "name": cfg["name"],
            "rss_url": cfg["rss_url"],
            "base_url": cfg["base_url"],
            "default_tags": cfg.get("default_tags", []),
        }

    html_sources = {}
    for source_id, cfg in (raw.get("html_sources") or {}).items():
        if not cfg.get("enabled", True):
            continue
        html_sources[source_id] = {
            "name": cfg["name"],
            "base_url": cfg["base_url"],
            "blog_path": cfg.get("blog_path", "/blog"),
            "default_tags": cfg.get("default_tags", []),
            "js_rendered": cfg.get("js_rendered", False),
        }

    filtering = raw.get("filtering") or {}
    global_config = raw.get("global") or {}

    return rss_feeds, html_sources, filtering, global_config


RSS_FEEDS, HTML_ONLY_SOURCES, FILTERING, GLOBAL_CONFIG = load_sources_config()


class UnifiedScraper:
    """
    Unified scraper that uses RSS when available, HTML as fallback.

    This is the recommended scraper for the Context Crew project.
    It's simpler, more reliable, and easier to maintain than separate scrapers.
    """

    def __init__(
        self,
        max_articles: int | None = None,
        rate_limit_seconds: float | None = None,
        lookback_days: int | None = None,
    ):
        self.max_articles = max_articles or settings.max_articles_per_source
        self.rate_limit_seconds = rate_limit_seconds or settings.scrape_delay_seconds
        self.lookback_days = lookback_days or GLOBAL_CONFIG.get("lookback_days", 60)
        self.request_timeout = GLOBAL_CONFIG.get(
            "request_timeout_seconds", settings.request_timeout_seconds
        )
        self.logger = get_logger("scraper.unified")
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a configured requests session."""
        session = requests.Session()
        user_agent = GLOBAL_CONFIG.get(
            "user_agent",
            "ContextCrewBot/1.0 (Academic Research; UW Capstone Project)",
        )
        session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
        )
        return session

    def _passes_filters(self, article: dict[str, Any]) -> bool:
        """Check if an article passes the date, keyword, and word-count filters."""
        # Date filter: skip articles older than lookback_days
        if self.lookback_days and article.get("published_date"):
            try:
                pub = date_parser.parse(article["published_date"])
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=UTC)
                cutoff = datetime.now(UTC) - timedelta(days=self.lookback_days)
                if pub < cutoff:
                    self.logger.debug(
                        f"Filtered out (too old, {pub.date()}): {article.get('title', '')}"
                    )
                    return False
            except (ValueError, TypeError):
                pass  # If date can't be parsed, don't filter it out

        min_wc = FILTERING.get("min_word_count", 0)
        max_wc = FILTERING.get("max_word_count", float("inf"))
        word_count = article.get("word_count", 0)

        if word_count < min_wc or word_count > max_wc:
            self.logger.debug(f"Filtered out (word count {word_count}): {article.get('title', '')}")
            return False

        keywords = FILTERING.get("relevant_keywords", [])
        if keywords:
            text = (article.get("title", "") + " " + article.get("content_text", "")).lower()
            if not any(kw.lower() in text for kw in keywords):
                self.logger.debug(f"Filtered out (no keyword match): {article.get('title', '')}")
                return False

        return True

    def _is_excluded_url(self, url: str) -> bool:
        """Check if a URL matches any exclude pattern from the config."""
        return any(pattern in url for pattern in FILTERING.get("exclude_patterns", []))

    def scrape_source(
        self, source_id: str, seen_urls: set[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Scrape a single source by ID.

        Automatically chooses RSS or HTML based on availability.
        Already-scraped URLs in ``seen_urls`` are skipped.
        """
        # Check if source has RSS
        if source_id in RSS_FEEDS:
            return self._scrape_rss(source_id, RSS_FEEDS[source_id], seen_urls)
        elif source_id in HTML_ONLY_SOURCES:
            return self._scrape_html(source_id, HTML_ONLY_SOURCES[source_id], seen_urls)
        else:
            self.logger.error(f"Unknown source: {source_id}")
            return []

    def scrape_all(
        self,
        sources: list[str] | None = None,
        seen_urls: set[str] | None = None,
    ) -> dict[str, list[dict]]:
        """
        Scrape multiple sources.

        Args:
            sources: List of source IDs to scrape. If None, scrapes all.
            seen_urls: URLs to skip (already scraped).

        Returns:
            Dictionary mapping source_id -> list of articles
        """
        if sources is None:
            sources = list(RSS_FEEDS.keys()) + list(HTML_ONLY_SOURCES.keys())

        results = {}
        for source_id in sources:
            self.logger.info(f"Scraping source: {source_id}")
            articles = self.scrape_source(source_id, seen_urls=seen_urls)
            results[source_id] = articles
            self.logger.info(f"Scraped {len(articles)} articles from {source_id}")

        return results

    # =========================================================================
    # RSS Scraping (Preferred)
    # =========================================================================

    def _scrape_rss(
        self, source_id: str, config: dict, seen_urls: set[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Scrape articles from an RSS feed.

        This is the preferred method - reliable and structured.
        Already-scraped URLs in ``seen_urls`` are skipped.
        """
        rss_url = config["rss_url"]
        self.logger.info(f"Fetching RSS feed: {rss_url}")

        try:
            feed = feedparser.parse(rss_url)

            if feed.bozo and feed.bozo_exception:
                self.logger.warning(f"RSS parse warning: {feed.bozo_exception}")

            if not feed.entries:
                self.logger.warning(f"No entries found in feed: {rss_url}")
                return []

            articles = []
            for entry in feed.entries[: self.max_articles]:
                # Skip excluded URLs early
                entry_url = entry.get("link", "")
                if entry_url and self._is_excluded_url(entry_url):
                    self.logger.debug(f"Skipping excluded URL: {entry_url}")
                    continue

                # Skip already-scraped URLs
                if seen_urls and entry_url in seen_urls:
                    self.logger.debug(f"Skipping already-scraped URL: {entry_url}")
                    continue

                article = self._rss_entry_to_article(entry, source_id, config)
                if article and self._passes_filters(article):
                    articles.append(article)

            return articles

        except Exception as e:
            self.logger.error(f"Failed to fetch RSS feed: {e}")
            return []

    def _rss_entry_to_article(
        self,
        entry: dict,
        source_id: str,
        config: dict,
    ) -> dict[str, Any] | None:
        """Convert an RSS feed entry to our article format."""
        try:
            # Extract URL
            url = entry.get("link", "")
            if not url:
                return None

            # Extract title
            title = entry.get("title", "").strip()
            if not title:
                return None

            # Extract content
            content_text = ""
            if entry.get("content"):
                # Full content available
                content_html = entry["content"][0].get("value", "")
                soup = BeautifulSoup(content_html, "lxml")
                content_text = soup.get_text(separator="\n", strip=True)
            elif entry.get("summary"):
                # Only summary available
                soup = BeautifulSoup(entry["summary"], "lxml")
                content_text = soup.get_text(separator="\n", strip=True)
            elif entry.get("description"):
                soup = BeautifulSoup(entry["description"], "lxml")
                content_text = soup.get_text(separator="\n", strip=True)

            # If content is too short, try fetching the full article
            if len(content_text) < 200:
                full_content = self._fetch_full_article(url)
                if full_content and len(full_content) > len(content_text):
                    content_text = full_content

            # Extract date
            published_date = None
            for date_field in ["published", "updated", "created"]:
                if entry.get(date_field):
                    try:
                        published_date = date_parser.parse(entry[date_field])
                        break
                    except (ValueError, TypeError):
                        continue

            # Extract author
            author = None
            if entry.get("author"):
                author = entry["author"]
            elif entry.get("authors"):
                author = ", ".join(a.get("name", "") for a in entry["authors"][:3])

            # Extract tags from RSS
            tags = list(config.get("default_tags", []))
            if entry.get("tags"):
                for tag in entry["tags"]:
                    if tag.get("term"):
                        tag_text = tag["term"].lower().strip()
                        if tag_text not in tags:
                            tags.append(tag_text)

            return self._create_article_dict(
                source_id=source_id,
                source_name=config["name"],
                url=url,
                title=title,
                content_text=content_text,
                author=author or config["name"],
                published_date=published_date,
                tags=tags,
            )

        except Exception as e:
            self.logger.warning(f"Failed to parse RSS entry: {e}")
            return None

    def _fetch_js_page(self, url: str) -> bytes | None:
        """Fetch a JS-rendered page using Playwright headless browser."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=30000)
                content = page.content().encode("utf-8")
                browser.close()
                return content
        except Exception as e:
            self.logger.debug(f"Playwright fetch failed for {url}: {e}")
            return None

    def _fetch_full_article(self, url: str) -> str | None:
        """Fetch full article content when RSS only has summary."""
        try:
            domain = urlparse(url).netloc
            rate_limiter.wait(domain)

            response = self.session.get(url, timeout=self.request_timeout)
            response.raise_for_status()

            text = trafilatura.extract(response.content, include_comments=False, include_tables=True)
            if text and len(text) > 200:
                return text

            return None

        except Exception as e:
            self.logger.debug(f"Could not fetch full article: {e}")
            return None

    # =========================================================================
    # HTML Scraping (Fallback)
    # =========================================================================

    def _scrape_html(
        self, source_id: str, config: dict, seen_urls: set[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Scrape articles by parsing HTML.

        Used as fallback when no RSS feed is available.
        Already-scraped URLs in ``seen_urls`` are skipped.
        """
        base_url = config["base_url"]
        blog_path = config.get("blog_path", "/blog")
        blog_url = f"{base_url}{blog_path}"

        self.logger.info(f"Scraping HTML: {blog_url}")

        # Get article URLs
        urls = self._discover_article_urls(blog_url, base_url, js_rendered=config.get("js_rendered", False))
        self.logger.info(f"Found {len(urls)} article URLs")

        # Remove already-scraped URLs
        if seen_urls:
            before = len(urls)
            urls = [u for u in urls if u not in seen_urls]
            skipped = before - len(urls)
            if skipped:
                self.logger.info(f"Skipped {skipped} already-scraped URLs")

        # Scrape each article
        articles = []
        for url in urls[: self.max_articles]:
            article = self._scrape_html_article(url, source_id, config)
            if article and self._passes_filters(article):
                articles.append(article)

        return articles

    def _discover_article_urls(self, blog_url: str, base_url: str, js_rendered: bool = False) -> list[str]:
        """Discover article URLs from a blog listing page."""
        try:
            domain = urlparse(blog_url).netloc
            rate_limiter.wait(domain)

            if js_rendered:
                html_content = self._fetch_js_page(blog_url)

            if not js_rendered or not html_content:
                response = self.session.get(blog_url, timeout=self.request_timeout)
                response.raise_for_status()
                html_content = response.content

            soup = BeautifulSoup(html_content, "lxml")
            urls = []

            for link in soup.find_all("a", href=True):
                href = link["href"]

                # Convert to absolute URL
                if href.startswith("/"):
                    full_url = f"{base_url}{href}"
                elif href.startswith("http"):
                    full_url = href
                else:
                    continue

                # Skip non-article URLs (built-in + config exclude_patterns)
                skip_patterns = [
                    r"^/?$",
                    r"/tag/",
                    r"/category/",
                    r"/author/",
                    r"/page/\d+",
                    r"/search",
                    r"/about",
                    r"/contact",
                    r"/products",
                    r"/solutions",
                    r"/platform",
                    r"/company",
                    r"/docs",
                    r"/api",
                    r"\.(jpg|png|gif|pdf|css|js)$",
                ]
                for ep in FILTERING.get("exclude_patterns", []):
                    skip_patterns.append(re.escape(ep))

                if any(re.search(p, href, re.I) for p in skip_patterns):
                    continue

                # Check if URL looks like an article (has a path segment)
                path = urlparse(full_url).path
                if (
                    path
                    and path != "/"
                    and full_url not in urls
                    and urlparse(full_url).netloc == urlparse(base_url).netloc
                ):
                    urls.append(full_url)

            return urls

        except Exception as e:
            self.logger.error(f"Failed to discover URLs: {e}")
            return []

    def _scrape_html_article(
        self,
        url: str,
        source_id: str,
        config: dict,
    ) -> dict[str, Any] | None:
        """Scrape a single article from HTML."""
        try:
            domain = urlparse(url).netloc
            rate_limiter.wait(domain)

            if config.get("js_rendered"):
                html_content = self._fetch_js_page(url)
                if not html_content:
                    return None
            else:
                response = self.session.get(url, timeout=self.request_timeout)
                response.raise_for_status()
                html_content = response.content

            # Use trafilatura for smart article extraction
            meta = trafilatura.extract_metadata(html_content, default_url=url)
            content_text = trafilatura.extract(
                html_content, include_comments=False, include_tables=True
            )

            if not content_text or len(content_text) < 200:
                return None

            # Get title from trafilatura metadata, fall back to og:title
            title = meta.title if meta else None
            if not title:
                soup = BeautifulSoup(html_content, "lxml")
                og = soup.select_one('meta[property="og:title"]')
                title = str(og.get("content") or "") if og else None
            if not title:
                return None

            # Get author and date from trafilatura metadata
            author = (meta.author if meta else None) or config["name"]
            published_date = None
            if meta and meta.date:
                try:
                    published_date = date_parser.parse(meta.date)
                except (ValueError, TypeError):
                    pass

            # Fallback date extraction if trafilatura couldn't find it
            if not published_date:
                published_date = self._extract_date_fallback(html_content, url)

            return self._create_article_dict(
                source_id=source_id,
                source_name=config["name"],
                url=url,
                title=title,
                content_text=content_text,
                author=author,
                published_date=published_date,
                tags=list(config.get("default_tags", [])),
            )

        except Exception as e:
            self.logger.warning(f"Failed to scrape article {url}: {e}")
            return None

    def _extract_date_fallback(self, html_content: bytes, url: str) -> Any | None:
        """
        Try harder to extract a publish date when trafilatura comes up empty.
        Checks JSON-LD, common meta tags, and <time> elements.
        """
        import json as _json
        import re as _re

        try:
            soup = BeautifulSoup(html_content, "lxml")

            # 1. JSON-LD structured data
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = _json.loads(script.string or "")
                    # Handle both single object and list
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        for field in ("datePublished", "dateCreated", "dateModified"):
                            val = item.get(field)
                            if val:
                                return date_parser.parse(val)
                except Exception:
                    continue

            # 2. Common meta tags
            meta_selectors = [
                'meta[property="article:published_time"]',
                'meta[name="publish_date"]',
                'meta[name="date"]',
                'meta[name="DC.date"]',
                'meta[itemprop="datePublished"]',
                'meta[property="og:published_time"]',
            ]
            for selector in meta_selectors:
                tag = soup.select_one(selector)
                if tag and tag.get("content"):
                    try:
                        return date_parser.parse(str(tag["content"]))
                    except (ValueError, TypeError):
                        continue

            # 3. <time> element with datetime attribute
            time_tag = soup.select_one("time[datetime]")
            if time_tag:
                try:
                    return date_parser.parse(str(time_tag["datetime"]))
                except (ValueError, TypeError):
                    pass

            # 4. URL date pattern (e.g. /2026/01/15/ or /2026-01-15-)
            match = _re.search(r"/(\d{4})[/-](\d{2})[/-](\d{2})", url)
            if match:
                try:
                    return date_parser.parse(f"{match.group(1)}-{match.group(2)}-{match.group(3)}")
                except (ValueError, TypeError):
                    pass

        except Exception:
            pass

        return None

    # =========================================================================
    # Helpers
    # =========================================================================

    def _create_article_dict(
        self,
        source_id: str,
        source_name: str,
        url: str,
        title: str,
        content_text: str,
        author: str,
        published_date: datetime | None,
        tags: list[str],
    ) -> dict[str, Any]:
        """Create a standardized article dictionary."""
        now = datetime.now(UTC)

        # Generate unique ID
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        article_id = f"{source_id}_{url_hash}"

        # Calculate word count
        word_count = len(content_text.split())

        # Generate summary
        summary = (
            content_text[:500].rsplit(" ", 1)[0] + "..."
            if len(content_text) > 500
            else content_text
        )

        return {
            "id": article_id,
            "source": source_id,
            "source_name": source_name,
            "url": url,
            "title": title,
            "author": author,
            "published_date": published_date.isoformat() if published_date else None,
            "scraped_at": now.isoformat(),
            "content_text": content_text,
            "summary": summary,
            "tags": list(set(tags)),
            "word_count": word_count,
            "metadata": {
                "reading_time_minutes": max(1, word_count // 200),
                "scrape_method": "rss" if source_id in RSS_FEEDS else "html",
            },
        }


# =============================================================================
# Convenience functions
# =============================================================================


def get_all_sources() -> dict[str, dict]:
    """Get all available sources (RSS + HTML)."""
    sources = {}

    for source_id, config in RSS_FEEDS.items():
        sources[source_id] = {
            **config,
            "method": "rss",
            "enabled": True,
        }

    for source_id, config in HTML_ONLY_SOURCES.items():
        sources[source_id] = {
            **config,
            "method": "html",
            "enabled": True,
        }

    return sources


def list_sources() -> None:
    """Print all available sources."""
    print("\n" + "=" * 70)
    print("AVAILABLE SOURCES")
    print("=" * 70)

    print("\n📡 RSS Sources (Preferred - More Reliable):")
    print("-" * 50)
    for source_id, config in RSS_FEEDS.items():
        print(f"  ✅ {source_id:25} - {config['name']}")

    print("\n🌐 HTML Sources (Fallback - May Break):")
    print("-" * 50)
    for source_id, config in HTML_ONLY_SOURCES.items():
        print(f"  ⚠️  {source_id:25} - {config['name']}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    # Quick test
    list_sources()

    scraper = UnifiedScraper(max_articles=3)

    # Test first available RSS source
    if RSS_FEEDS:
        first_source = next(iter(RSS_FEEDS))
        print(f"\nTesting {first_source} (RSS)...")
        articles = scraper.scrape_source(first_source)
        for a in articles:
            print(f"  - {a['title'][:60]}...")
