"""
Scraper for Hugging Face blog.
https://huggingface.co/blog
"""

import re
from typing import Any, Optional

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper


class HuggingFaceScraper(BaseScraper):
    """
    Scraper for Hugging Face's blog.
    
    Hugging Face publishes model releases, tutorials, and research updates.
    """
    
    def __init__(self, **kwargs):
        super().__init__(
            source_name="HuggingFace",
            base_url="https://huggingface.co",
            blog_path="/blog",
            **kwargs,
        )
    
    def get_article_urls(self) -> list[str]:
        """Get article URLs from Hugging Face blog."""
        urls = []
        
        soup = self.fetch_page(self.blog_url)
        if not soup:
            self.logger.error("Failed to fetch Hugging Face blog page")
            return urls
        
        # Find article links - HF blog uses /blog/slug pattern
        for link in soup.find_all("a", href=True):
            href = link["href"]
            
            # Match /blog/something patterns
            if re.match(r"^/blog/[a-zA-Z0-9_-]+$", href):
                full_url = self.normalize_url(href)
                if full_url not in urls:
                    urls.append(full_url)
            elif re.match(r"^https://huggingface\.co/blog/[a-zA-Z0-9_-]+$", href):
                if href not in urls:
                    urls.append(href)
        
        self.logger.info(f"Found {len(urls)} Hugging Face article URLs")
        return urls
    
    def scrape_article(self, url: str) -> Optional[dict[str, Any]]:
        """Scrape a single Hugging Face article."""
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        html_content = self.fetch_html(url) or ""
        
        # Extract title
        title = None
        title_elem = soup.select_one("h1")
        if title_elem:
            title = title_elem.get_text(strip=True)
        else:
            meta = soup.select_one('meta[property="og:title"]')
            if meta:
                title = meta.get("content")
        
        if not title:
            return None
        
        # Extract content - HF uses markdown rendered to HTML
        content_selectors = [
            "article",
            ".blog-content",
            '[class*="prose"]',
            "main",
            ".container",
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
                "time",
                '[class*="date"]',
                ".text-gray-500",  # HF often uses gray text for dates
            ],
            meta_names=[
                "article:published_time",
                "og:published_time",
            ],
        )
        
        # Extract author(s) - HF often has multiple authors
        authors = []
        author_elems = soup.select('[class*="author"] a, .text-gray-700 a')
        for elem in author_elems:
            author_name = elem.get_text(strip=True)
            if author_name and len(author_name) < 100:
                authors.append(author_name)
        
        author = ", ".join(authors[:3]) if authors else None  # Limit to 3 authors
        
        # If no author found, try meta
        if not author:
            author = self.extract_author(
                soup,
                selectors=[],
                meta_names=["author"],
            )
        
        # Extract/infer tags
        tags = ["huggingface", "transformers"]
        
        # Check URL slug and title for topic indicators
        url_slug = url.split("/")[-1].lower()
        title_lower = title.lower()
        combined = f"{url_slug} {title_lower}"
        
        tag_keywords = {
            "llm": "llm",
            "bert": "bert",
            "gpt": "gpt",
            "diffusion": "diffusion",
            "stable": "stable-diffusion",
            "fine-tun": "fine-tuning",
            "training": "training",
            "dataset": "datasets",
            "embedding": "embeddings",
            "rag": "rag",
            "retrieval": "retrieval",
            "inference": "inference",
            "quantiz": "quantization",
            "agent": "agents",
            "text-generation": "text-generation",
            "vision": "vision",
            "multimodal": "multimodal",
        }
        
        for keyword, tag in tag_keywords.items():
            if keyword in combined:
                tags.append(tag)
        
        return self.create_article_dict(
            url=url,
            title=title,
            content_text=content_text,
            content_html=html_content,
            author=author or "Hugging Face Team",
            published_date=published_date,
            tags=list(set(tags)),
        )
