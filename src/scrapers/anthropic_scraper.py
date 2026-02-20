"""
Scraper for Anthropic's research blog.
https://www.anthropic.com/research
"""

import re
from typing import Any

from .base_scraper import BaseScraper


class AnthropicScraper(BaseScraper):
    """
    Scraper for Anthropic's research and news blog.

    Anthropic publishes research papers, safety updates, and product announcements.
    """

    def __init__(self, **kwargs):
        super().__init__(
            source_name="Anthropic",
            base_url="https://www.anthropic.com",
            blog_path="/research",
            **kwargs,
        )

    def get_article_urls(self) -> list[str]:
        """
        Get article URLs from Anthropic's research page.

        The research page typically lists articles with links.
        """
        urls = []

        # Scrape main research page
        soup = self.fetch_page(self.blog_url)
        if not soup:
            self.logger.error("Failed to fetch Anthropic research page")
            return urls

        # Find article links - Anthropic uses various patterns
        # Look for links containing /research/ or /news/
        link_patterns = [
            r"^/research/[^/]+$",
            r"^/news/[^/]+$",
            r"^https://www\.anthropic\.com/research/[^/]+$",
            r"^https://www\.anthropic\.com/news/[^/]+$",
        ]

        for link in soup.find_all("a", href=True):
            href = link["href"]

            for pattern in link_patterns:
                if re.match(pattern, href):
                    full_url = self.normalize_url(href)
                    if full_url not in urls:
                        urls.append(full_url)
                    break

        # Also try the news section
        news_soup = self.fetch_page(f"{self.base_url}/news")
        if news_soup:
            for link in news_soup.find_all("a", href=True):
                href = link["href"]
                for pattern in link_patterns:
                    if re.match(pattern, href):
                        full_url = self.normalize_url(href)
                        if full_url not in urls:
                            urls.append(full_url)
                        break

        self.logger.info(f"Found {len(urls)} Anthropic article URLs")
        return urls

    def scrape_article(self, url: str) -> dict[str, Any] | None:
        """Scrape a single Anthropic article."""
        soup = self.fetch_page(url)
        if not soup:
            return None

        html_content = self.fetch_html(url) or ""

        # Extract title
        title = None
        title_selectors = [
            "h1",
            'meta[property="og:title"]',
            'meta[name="title"]',
        ]
        for selector in title_selectors:
            if selector.startswith("meta"):
                meta = soup.select_one(selector)
                if meta:
                    title = meta.get("content")
                    break
            else:
                elem = soup.select_one(selector)
                if elem:
                    title = elem.get_text(strip=True)
                    break

        if not title:
            self.logger.warning("Could not extract title", url=url)
            return None

        # Extract main content
        content_selectors = [
            "article",
            "main",
            '[class*="content"]',
            '[class*="post"]',
            '[class*="article"]',
        ]

        content_text = ""
        for selector in content_selectors:
            content_text = self.extract_text_content(soup, selector)
            if len(content_text) > 200:  # Minimum viable content
                break

        if len(content_text) < 200:
            self.logger.warning("Content too short", url=url, length=len(content_text))
            return None

        # Extract date
        published_date = self.extract_date(
            soup,
            selectors=[
                "time",
                '[class*="date"]',
                '[class*="published"]',
            ],
            meta_names=[
                "article:published_time",
                "og:published_time",
                "datePublished",
            ],
        )

        # Extract author
        author = self.extract_author(
            soup,
            selectors=[
                '[class*="author"]',
                '[rel="author"]',
            ],
            meta_names=[
                "author",
                "article:author",
            ],
        )

        # Extract tags/categories
        tags = []
        for tag_elem in soup.select('[class*="tag"], [class*="category"]'):
            tag_text = tag_elem.get_text(strip=True).lower()
            if tag_text and len(tag_text) < 50:
                tags.append(tag_text)

        # Add default tags based on URL
        if "/research/" in url:
            tags.append("research")
        if "/news/" in url:
            tags.append("news")
        tags.append("anthropic")
        tags.append("claude")

        return self.create_article_dict(
            url=url,
            title=title,
            content_text=content_text,
            content_html=html_content,
            author=author or "Anthropic",
            published_date=published_date,
            tags=list(set(tags)),
        )
