"""
Generic scraper for blogs with standard HTML structure.
Works with RSS feeds or standard blog layouts.
"""

import re
from typing import Any
from urllib.parse import urlparse

import feedparser
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper


class GenericScraper(BaseScraper):
    """
    Generic scraper that works with most blog formats.

    Attempts to use RSS feed first, then falls back to HTML scraping.
    """

    RSS_PATHS = [
        "/feed",
        "/feed/",
        "/rss",
        "/rss/",
        "/feed.xml",
        "/rss.xml",
        "/atom.xml",
        "/blog/feed",
        "/blog/rss",
    ]

    def __init__(
        self,
        source_name: str,
        base_url: str,
        blog_path: str = "/blog",
        rss_url: str | None = None,
        **kwargs
    ):
        super().__init__(
            source_name=source_name,
            base_url=base_url,
            blog_path=blog_path,
            **kwargs,
        )
        self.rss_url = rss_url
        self._rss_feed = None

    def _find_rss_feed(self) -> str | None:
        """Attempt to discover RSS feed URL."""
        if self.rss_url:
            return self.rss_url

        # Try common RSS paths
        for path in self.RSS_PATHS:
            test_url = f"{self.base_url}{path}"
            try:
                feed = feedparser.parse(test_url)
                if feed.entries:
                    self.logger.info(f"Found RSS feed at {test_url}")
                    return test_url
            except Exception:
                continue

        # Try to find RSS link in HTML
        soup = self.fetch_page(self.blog_url)
        if soup:
            rss_link = soup.find("link", {"type": "application/rss+xml"})
            if rss_link and rss_link.get("href"):
                return self.normalize_url(rss_link["href"])

            atom_link = soup.find("link", {"type": "application/atom+xml"})
            if atom_link and atom_link.get("href"):
                return self.normalize_url(atom_link["href"])

        return None

    def get_article_urls(self) -> list[str]:
        """Get article URLs from RSS feed or HTML scraping."""
        urls = []

        # Try RSS first
        rss_url = self._find_rss_feed()
        if rss_url:
            feed = feedparser.parse(rss_url)
            self._rss_feed = feed  # Cache for article scraping

            for entry in feed.entries[:self.max_articles]:
                if entry.get("link"):
                    urls.append(entry.link)

            if urls:
                self.logger.info(f"Got {len(urls)} URLs from RSS feed")
                return urls

        # Fall back to HTML scraping
        return self._scrape_article_urls_from_html()

    def _scrape_article_urls_from_html(self) -> list[str]:
        """Scrape article URLs from HTML blog listing."""
        urls = []

        soup = self.fetch_page(self.blog_url)
        if not soup:
            return urls

        domain = urlparse(self.base_url).netloc

        # Find all links and filter for blog posts
        for link in soup.find_all("a", href=True):
            href = link["href"]
            full_url = self.normalize_url(href)

            # Must be on same domain
            if urlparse(full_url).netloc != domain:
                continue

            # Skip common non-article patterns
            skip_patterns = [
                r"^/?$",
                r"^#",
                r"/tag/",
                r"/category/",
                r"/author/",
                r"/page/\d+",
                r"/archive",
                r"/about",
                r"/contact",
                r"/privacy",
                r"/terms",
                r"/search",
                r"\.(jpg|png|gif|pdf|css|js)$",
            ]

            if any(re.search(pattern, href, re.I) for pattern in skip_patterns):
                continue

            # Check if URL looks like a blog post
            # Usually has a slug or date pattern
            path = urlparse(full_url).path
            if (re.search(r"/\d{4}/\d{2}/", path) or len(path.split("/")) >= 2) and full_url not in urls and full_url != self.blog_url:
                urls.append(full_url)

        return urls[:self.max_articles]

    def scrape_article(self, url: str) -> dict[str, Any] | None:
        """Scrape a single article."""
        # Check if we have RSS data for this article
        rss_entry = self._get_rss_entry(url)

        soup = self.fetch_page(url)
        if not soup:
            return None

        html_content = self.fetch_html(url) or ""

        # Extract title
        title = self._extract_title(soup, rss_entry)
        if not title:
            return None

        # Extract content
        content_text = self._extract_content(soup, rss_entry)
        if len(content_text) < 200:
            return None

        # Extract date
        published_date = self._extract_date(soup, rss_entry)

        # Extract author
        author = self._extract_author(soup, rss_entry)

        # Extract tags
        tags = self._extract_tags(soup, rss_entry)
        tags.append(self.source_name.lower().replace(" ", "-"))

        return self.create_article_dict(
            url=url,
            title=title,
            content_text=content_text,
            content_html=html_content,
            author=author,
            published_date=published_date,
            tags=list(set(tags)),
        )

    def _get_rss_entry(self, url: str) -> dict | None:
        """Get RSS entry for a URL if available."""
        if not self._rss_feed:
            return None

        for entry in self._rss_feed.entries:
            if entry.get("link") == url:
                return entry
        return None

    def _extract_title(self, soup: BeautifulSoup, rss_entry: dict | None) -> str | None:
        """Extract article title."""
        # Try RSS first
        if rss_entry and rss_entry.get("title"):
            return rss_entry["title"]

        # Try common HTML patterns
        selectors = [
            "h1.post-title",
            "h1.entry-title",
            "article h1",
            "h1",
            'meta[property="og:title"]',
        ]

        for selector in selectors:
            if selector.startswith("meta"):
                meta = soup.select_one(selector)
                if meta and meta.get("content"):
                    return meta["content"]
            else:
                elem = soup.select_one(selector)
                if elem:
                    return elem.get_text(strip=True)

        return None

    def _extract_content(self, soup: BeautifulSoup, rss_entry: dict | None) -> str:
        """Extract article content."""
        # Try HTML first for full content
        selectors = [
            "article .content",
            "article .post-content",
            ".post-body",
            ".entry-content",
            "article",
            "main .content",
            "main",
        ]

        for selector in selectors:
            content = self.extract_text_content(soup, selector)
            if len(content) > 300:
                return content

        # Fall back to RSS content/summary
        if rss_entry:
            if rss_entry.get("content"):
                content_html = rss_entry["content"][0].get("value", "")
                content_soup = BeautifulSoup(content_html, "lxml")
                return content_soup.get_text(separator="\n", strip=True)
            if rss_entry.get("summary"):
                summary_soup = BeautifulSoup(rss_entry["summary"], "lxml")
                return summary_soup.get_text(separator="\n", strip=True)

        return ""

    def _extract_date(self, soup: BeautifulSoup, rss_entry: dict | None):
        """Extract publication date."""
        from dateutil import parser as date_parser

        # Try RSS first
        if rss_entry:
            for field in ["published", "updated", "created"]:
                if rss_entry.get(field):
                    try:
                        return date_parser.parse(rss_entry[field])
                    except (ValueError, TypeError):
                        pass

        # Try HTML
        return self.extract_date(
            soup,
            selectors=[
                "time.published",
                "time.post-date",
                "time",
                ".post-meta time",
                '[class*="date"]',
            ],
            meta_names=[
                "article:published_time",
                "datePublished",
            ],
        )

    def _extract_author(self, soup: BeautifulSoup, rss_entry: dict | None) -> str | None:
        """Extract author name."""
        # Try RSS
        if rss_entry:
            if rss_entry.get("author"):
                return rss_entry["author"]
            if rss_entry.get("authors"):
                return ", ".join(a.get("name", "") for a in rss_entry["authors"][:3])

        # Try HTML
        return self.extract_author(
            soup,
            selectors=[
                ".post-author",
                ".author-name",
                '[rel="author"]',
                '[class*="author"]',
            ],
            meta_names=["author"],
        )

    def _extract_tags(self, soup: BeautifulSoup, rss_entry: dict | None) -> list[str]:
        """Extract tags/categories."""
        tags = []

        # Try RSS
        if rss_entry and rss_entry.get("tags"):
            for tag in rss_entry["tags"]:
                if tag.get("term"):
                    tags.append(tag["term"].lower())

        # Try HTML
        for tag_elem in soup.select(".post-tag, .tag, .category, [rel='tag']"):
            tag_text = tag_elem.get_text(strip=True).lower()
            if tag_text and len(tag_text) < 50 and tag_text not in tags:
                tags.append(tag_text)

        return tags[:10]  # Limit tags
