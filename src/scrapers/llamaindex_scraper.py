"""
Scraper for LlamaIndex blog.
https://www.llamaindex.ai/blog
"""

import re
from typing import Any, Optional

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper


class LlamaIndexScraper(BaseScraper):
    """
    Scraper for LlamaIndex's technical blog.
    
    LlamaIndex publishes tutorials, announcements, and deep-dives on RAG.
    """
    
    def __init__(self, **kwargs):
        super().__init__(
            source_name="LlamaIndex",
            base_url="https://www.llamaindex.ai",
            blog_path="/blog",
            **kwargs,
        )
    
    def get_article_urls(self) -> list[str]:
        """Get article URLs from LlamaIndex blog."""
        urls = []
        
        soup = self.fetch_page(self.blog_url)
        if not soup:
            self.logger.error("Failed to fetch LlamaIndex blog page")
            return urls
        
        # Find article links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            
            # Match blog post patterns
            if "/blog/" in href and href != "/blog/" and href != "/blog":
                full_url = self.normalize_url(href)
                
                # Skip category/tag pages
                if any(x in full_url for x in ["/category/", "/tag/", "/page/"]):
                    continue
                
                if full_url not in urls:
                    urls.append(full_url)
        
        # Try pagination if available
        page = 2
        while len(urls) < self.max_articles and page <= 10:
            page_url = f"{self.blog_url}?page={page}"
            page_soup = self.fetch_page(page_url)
            
            if not page_soup:
                break
            
            new_urls_found = False
            for link in page_soup.find_all("a", href=True):
                href = link["href"]
                if "/blog/" in href and href not in ["/blog/", "/blog"]:
                    full_url = self.normalize_url(href)
                    if any(x in full_url for x in ["/category/", "/tag/", "/page/"]):
                        continue
                    if full_url not in urls:
                        urls.append(full_url)
                        new_urls_found = True
            
            if not new_urls_found:
                break
            page += 1
        
        self.logger.info(f"Found {len(urls)} LlamaIndex article URLs")
        return urls
    
    def scrape_article(self, url: str) -> Optional[dict[str, Any]]:
        """Scrape a single LlamaIndex article."""
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        html_content = self.fetch_html(url) or ""
        
        # Extract title
        title = None
        for selector in ["h1", 'meta[property="og:title"]']:
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
            return None
        
        # Extract content
        content_selectors = [
            "article",
            '[class*="blog-content"]',
            '[class*="post-content"]',
            '[class*="content"]',
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
            selectors=["time", '[class*="date"]'],
            meta_names=["article:published_time", "datePublished"],
        )
        
        # Extract author
        author = self.extract_author(
            soup,
            selectors=['[class*="author"]', '[rel="author"]'],
            meta_names=["author"],
        )
        
        # Extract tags
        tags = ["llamaindex", "rag", "retrieval"]
        
        # Look for category/topic indicators in URL or content
        url_lower = url.lower()
        if "tutorial" in url_lower or "how-to" in url_lower:
            tags.append("tutorial")
        if "announcement" in url_lower or "release" in url_lower:
            tags.append("announcement")
        if "agent" in url_lower:
            tags.append("agents")
        
        return self.create_article_dict(
            url=url,
            title=title,
            content_text=content_text,
            content_html=html_content,
            author=author or "LlamaIndex Team",
            published_date=published_date,
            tags=list(set(tags)),
        )
