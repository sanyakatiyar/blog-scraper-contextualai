"""
Base scraper class that all blog scrapers inherit from.
"""

import hashlib
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config.settings import settings
from src.utils import get_logger, rate_limiter


class BaseScraper(ABC):
    """
    Abstract base class for blog scrapers.
    
    Provides common functionality for HTTP requests, rate limiting,
    content extraction, and data normalization.
    """
    
    def __init__(
        self,
        source_name: str,
        base_url: str,
        blog_path: str = "",
        max_articles: int | None = None,
        rate_limit_seconds: float | None = None,
    ):
        self.source_name = source_name
        self.base_url = base_url.rstrip("/")
        self.blog_path = blog_path
        self.max_articles = max_articles or settings.max_articles_per_source
        self.rate_limit_seconds = rate_limit_seconds or settings.scrape_delay_seconds
        
        self.logger = get_logger(f"scraper.{source_name}")
        self.session = self._create_session()
        
        # Set up rate limiting for this domain
        domain = urlparse(self.base_url).netloc
        rate_limiter.set_domain_delay(domain, self.rate_limit_seconds)
    
    def _create_session(self) -> requests.Session:
        """Create a configured requests session."""
        session = requests.Session()
        session.headers.update({
            "User-Agent": "ContextCrewBot/1.0 (Academic Research; UW Capstone Project)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        })
        return session
    
    @property
    def blog_url(self) -> str:
        """Full URL to the blog listing page."""
        return f"{self.base_url}{self.blog_path}"
    
    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """
        Fetch a page and return parsed BeautifulSoup object.
        
        Handles rate limiting and error handling.
        """
        domain = urlparse(url).netloc
        rate_limiter.wait(domain)
        
        try:
            self.logger.debug("Fetching page", url=url)
            response = self.session.get(
                url,
                timeout=settings.request_timeout_seconds,
            )
            response.raise_for_status()
            
            return BeautifulSoup(response.content, "lxml")
            
        except requests.RequestException as e:
            self.logger.error("Failed to fetch page", url=url, error=str(e))
            return None
    
    def fetch_html(self, url: str) -> Optional[str]:
        """Fetch raw HTML content from a URL."""
        domain = urlparse(url).netloc
        rate_limiter.wait(domain)
        
        try:
            response = self.session.get(
                url,
                timeout=settings.request_timeout_seconds,
            )
            response.raise_for_status()
            return response.text
            
        except requests.RequestException as e:
            self.logger.error("Failed to fetch HTML", url=url, error=str(e))
            return None
    
    @abstractmethod
    def get_article_urls(self) -> list[str]:
        """
        Discover article URLs from the blog.
        
        Must be implemented by subclasses for each specific blog.
        Returns a list of full article URLs.
        """
        pass
    
    @abstractmethod
    def scrape_article(self, url: str) -> Optional[dict[str, Any]]:
        """
        Scrape a single article and return structured data.
        
        Must be implemented by subclasses for each specific blog.
        Returns a dictionary following the article schema, or None on failure.
        """
        pass
    
    def scrape_all(self) -> list[dict[str, Any]]:
        """
        Scrape all articles from this blog source.
        
        Returns a list of article dictionaries.
        """
        self.logger.info(
            "Starting scrape",
            source=self.source_name,
            max_articles=self.max_articles,
        )
        
        # Get article URLs
        urls = self.get_article_urls()
        self.logger.info(f"Found {len(urls)} article URLs")
        
        # Limit to max articles
        urls = urls[:self.max_articles]
        
        # Scrape each article
        articles = []
        for i, url in enumerate(urls):
            self.logger.debug(f"Scraping article {i+1}/{len(urls)}", url=url)
            
            article = self.scrape_article(url)
            if article:
                articles.append(article)
            else:
                self.logger.warning("Failed to scrape article", url=url)
        
        self.logger.info(
            "Scrape complete",
            source=self.source_name,
            total_scraped=len(articles),
        )
        
        return articles
    
    # --- Helper Methods ---
    
    def normalize_url(self, url: str) -> str:
        """Convert relative URLs to absolute URLs."""
        if url.startswith("http"):
            return url
        return urljoin(self.base_url, url)
    
    def generate_article_id(self, url: str) -> str:
        """Generate a unique ID for an article based on its URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        source_prefix = self.source_name.lower().replace(" ", "_")[:10]
        return f"{source_prefix}_{url_hash}"
    
    def extract_text_content(self, soup: BeautifulSoup, selector: str) -> str:
        """Extract and clean text content from a BeautifulSoup element."""
        element = soup.select_one(selector)
        if not element:
            return ""
        
        # Remove script and style elements
        for tag in element.find_all(["script", "style", "nav", "footer"]):
            tag.decompose()
        
        # Get text and clean it
        text = element.get_text(separator="\n", strip=True)
        
        # Clean up whitespace
        text = re.sub(r"\n\s*\n", "\n\n", text)
        text = re.sub(r" +", " ", text)
        
        return text.strip()
    
    def extract_date(
        self,
        soup: BeautifulSoup,
        selectors: list[str],
        meta_names: list[str] | None = None,
    ) -> Optional[datetime]:
        """
        Try to extract publication date from various sources.
        
        Args:
            soup: BeautifulSoup object
            selectors: CSS selectors to try
            meta_names: Meta tag names to check
        """
        from dateutil import parser as date_parser
        
        # Try CSS selectors first
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                date_str = element.get("datetime") or element.get_text(strip=True)
                try:
                    return date_parser.parse(date_str)
                except (ValueError, TypeError):
                    continue
        
        # Try meta tags
        if meta_names:
            for name in meta_names:
                meta = soup.find("meta", {"property": name}) or soup.find("meta", {"name": name})
                if meta and meta.get("content"):
                    try:
                        return date_parser.parse(meta["content"])
                    except (ValueError, TypeError):
                        continue
        
        return None
    
    def extract_author(
        self,
        soup: BeautifulSoup,
        selectors: list[str],
        meta_names: list[str] | None = None,
    ) -> Optional[str]:
        """Extract author name from various sources."""
        # Try CSS selectors
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                author = element.get_text(strip=True)
                if author:
                    return author
        
        # Try meta tags
        if meta_names:
            for name in meta_names:
                meta = soup.find("meta", {"property": name}) or soup.find("meta", {"name": name})
                if meta and meta.get("content"):
                    return meta["content"]
        
        return None
    
    def create_article_dict(
        self,
        url: str,
        title: str,
        content_text: str,
        content_html: str = "",
        author: str | None = None,
        published_date: datetime | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a standardized article dictionary."""
        now = datetime.now(timezone.utc)
        
        # Calculate word count
        word_count = len(content_text.split())
        
        # Generate summary (first 500 chars)
        summary = content_text[:500].rsplit(" ", 1)[0] + "..." if len(content_text) > 500 else content_text
        
        # Check for code blocks
        has_code_blocks = bool(
            re.search(r"```|<pre>|<code>", content_html) or
            re.search(r"^\s{4,}\S", content_text, re.MULTILINE)
        )
        
        return {
            "id": self.generate_article_id(url),
            "source": self.source_name.lower().replace(" ", "_"),
            "source_name": self.source_name,
            "url": url,
            "title": title,
            "author": author or "Unknown",
            "published_date": published_date.isoformat() if published_date else None,
            "scraped_at": now.isoformat(),
            "content_text": content_text,
            "content_html": content_html if settings.enable_html_snapshots else "",
            "summary": summary,
            "tags": tags or [],
            "word_count": word_count,
            "metadata": {
                "reading_time_minutes": max(1, word_count // 200),
                "has_code_blocks": has_code_blocks,
                "has_images": bool(re.search(r"<img\s", content_html)),
                **(metadata or {}),
            },
        }
