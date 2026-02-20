"""
Scraper for LangChain blog.
https://blog.langchain.dev
"""

import re
from typing import Any

from .base_scraper import BaseScraper


class LangChainScraper(BaseScraper):
    """
    Scraper for LangChain's developer blog.

    LangChain publishes tutorials, release notes, and case studies.
    """

    def __init__(self, **kwargs):
        super().__init__(
            source_name="LangChain",
            base_url="https://blog.langchain.dev",
            blog_path="",
            **kwargs,
        )

    def get_article_urls(self) -> list[str]:
        """Get article URLs from LangChain blog."""
        urls = []

        soup = self.fetch_page(self.blog_url)
        if not soup:
            self.logger.error("Failed to fetch LangChain blog page")
            return urls

        # LangChain blog uses Ghost or similar - look for post links
        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Skip non-article links
            skip_patterns = [
                r"^/?$",
                r"^#",
                r"/tag/",
                r"/author/",
                r"/page/",
                r"twitter\.com",
                r"github\.com",
                r"linkedin\.com",
            ]

            if any(re.search(pattern, href) for pattern in skip_patterns):
                continue

            # Check if it looks like a blog post URL
            full_url = self.normalize_url(href)

            # LangChain blog posts are usually at the root with slug
            if full_url.startswith(self.base_url):
                path = full_url.replace(self.base_url, "").strip("/")

                # Valid post: has a slug, no special characters indicating category
                if path and "/" not in path and not path.startswith(("tag", "author", "page")) and full_url not in urls:
                    urls.append(full_url)

        # Handle pagination
        page = 2
        while len(urls) < self.max_articles and page <= 10:
            page_url = f"{self.blog_url}/page/{page}/"
            page_soup = self.fetch_page(page_url)

            if not page_soup:
                break

            initial_count = len(urls)
            for link in page_soup.find_all("a", href=True):
                href = link["href"]
                full_url = self.normalize_url(href)

                if full_url.startswith(self.base_url):
                    path = full_url.replace(self.base_url, "").strip("/")
                    if path and "/" not in path and not path.startswith(("tag", "author", "page")) and full_url not in urls:
                        urls.append(full_url)

            if len(urls) == initial_count:
                break
            page += 1

        self.logger.info(f"Found {len(urls)} LangChain article URLs")
        return urls

    def scrape_article(self, url: str) -> dict[str, Any] | None:
        """Scrape a single LangChain article."""
        soup = self.fetch_page(url)
        if not soup:
            return None

        html_content = self.fetch_html(url) or ""

        # Extract title
        title = None
        title_elem = soup.select_one("h1.post-title") or soup.select_one("h1")
        if title_elem:
            title = title_elem.get_text(strip=True)
        else:
            meta = soup.select_one('meta[property="og:title"]')
            if meta:
                title = meta.get("content")

        if not title:
            return None

        # Extract content
        content_selectors = [
            "article .post-content",
            "article",
            ".post-content",
            ".gh-content",
            "main",
        ]

        content_text = ""
        for selector in content_selectors:
            content_text = self.extract_text_content(soup, selector)
            if len(content_text) > 200:
                break

        if len(content_text) < 200:
            return None

        # Extract date
        published_date = self.extract_date(
            soup,
            selectors=[
                "time.post-date",
                "time",
                ".post-meta time",
                '[class*="date"]',
            ],
            meta_names=["article:published_time"],
        )

        # Extract author
        author = self.extract_author(
            soup,
            selectors=[
                ".post-author-name",
                ".author-name",
                '[class*="author"]',
            ],
            meta_names=["author"],
        )

        # Extract tags from the page
        tags = ["langchain"]
        for tag_elem in soup.select(".post-tag, .tag"):
            tag_text = tag_elem.get_text(strip=True).lower()
            if tag_text and len(tag_text) < 30:
                tags.append(tag_text)

        # Infer tags from title/content
        keywords_to_tags = {
            "langgraph": "langgraph",
            "langsmith": "langsmith",
            "agent": "agents",
            "rag": "rag",
            "retrieval": "retrieval",
            "chain": "chains",
            "tool": "tools",
            "memory": "memory",
        }

        title_lower = title.lower()
        for keyword, tag in keywords_to_tags.items():
            if keyword in title_lower:
                tags.append(tag)

        return self.create_article_dict(
            url=url,
            title=title,
            content_text=content_text,
            content_html=html_content,
            author=author or "LangChain Team",
            published_date=published_date,
            tags=list(set(tags)),
        )
