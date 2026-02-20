"""
Tests for blog scrapers.

Run with: pytest tests/test_scrapers.py -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from src.scrapers import (
    BaseScraper,
    AnthropicScraper,
    LlamaIndexScraper,
    LangChainScraper,
    HuggingFaceScraper,
    GenericScraper,
    get_scraper,
    SCRAPER_REGISTRY,
)


class TestScraperRegistry:
    """Test scraper registry functionality."""
    
    def test_get_valid_scraper(self):
        """Test getting a valid scraper class."""
        scraper_class = get_scraper("AnthropicScraper")
        assert scraper_class == AnthropicScraper
    
    def test_get_invalid_scraper(self):
        """Test getting an invalid scraper raises error."""
        with pytest.raises(ValueError, match="Unknown scraper"):
            get_scraper("NonExistentScraper")
    
    def test_all_scrapers_registered(self):
        """Test that all expected scrapers are registered."""
        expected = [
            "AnthropicScraper",
            "LlamaIndexScraper",
            "LangChainScraper",
            "HuggingFaceScraper",
            "GenericScraper",
        ]
        for name in expected:
            assert name in SCRAPER_REGISTRY


class TestBaseScraper:
    """Test base scraper functionality."""
    
    def test_normalize_url_absolute(self):
        """Test that absolute URLs are preserved."""
        scraper = GenericScraper(
            source_name="Test",
            base_url="https://example.com",
        )
        url = scraper.normalize_url("https://other.com/page")
        assert url == "https://other.com/page"
    
    def test_normalize_url_relative(self):
        """Test that relative URLs are converted to absolute."""
        scraper = GenericScraper(
            source_name="Test",
            base_url="https://example.com",
        )
        url = scraper.normalize_url("/blog/post")
        assert url == "https://example.com/blog/post"
    
    def test_generate_article_id(self):
        """Test article ID generation is deterministic."""
        scraper = GenericScraper(
            source_name="Test",
            base_url="https://example.com",
        )
        url = "https://example.com/blog/my-post"
        id1 = scraper.generate_article_id(url)
        id2 = scraper.generate_article_id(url)
        
        assert id1 == id2
        assert id1.startswith("test_")
        assert len(id1) > 10
    
    def test_create_article_dict(self):
        """Test article dictionary creation."""
        scraper = GenericScraper(
            source_name="Test Source",
            base_url="https://example.com",
        )
        
        article = scraper.create_article_dict(
            url="https://example.com/post",
            title="Test Title",
            content_text="This is test content with some words.",
            author="Test Author",
        )
        
        assert article["title"] == "Test Title"
        assert article["source_name"] == "Test Source"
        assert article["author"] == "Test Author"
        assert article["word_count"] == 7
        assert "id" in article
        assert "scraped_at" in article
        assert "metadata" in article


class TestAnthropicScraper:
    """Test Anthropic scraper."""
    
    def test_initialization(self):
        """Test scraper initializes correctly."""
        scraper = AnthropicScraper()
        
        assert scraper.source_name == "Anthropic"
        assert scraper.base_url == "https://www.anthropic.com"
        assert "/research" in scraper.blog_path
    
    @patch.object(AnthropicScraper, 'fetch_page')
    def test_get_article_urls(self, mock_fetch):
        """Test URL extraction from Anthropic research page."""
        # Create mock HTML
        html = """
        <html>
        <body>
            <a href="/research/claude-3">Claude 3</a>
            <a href="/research/constitutional-ai">Constitutional AI</a>
            <a href="/news/announcement">News Item</a>
            <a href="/careers">Careers</a>
        </body>
        </html>
        """
        from bs4 import BeautifulSoup
        mock_fetch.return_value = BeautifulSoup(html, "lxml")
        
        scraper = AnthropicScraper()
        urls = scraper.get_article_urls()
        
        # Should find research and news articles, not careers
        assert len(urls) >= 2
        assert any("/research/claude-3" in url for url in urls)


class TestLlamaIndexScraper:
    """Test LlamaIndex scraper."""
    
    def test_initialization(self):
        """Test scraper initializes correctly."""
        scraper = LlamaIndexScraper()
        
        assert scraper.source_name == "LlamaIndex"
        assert "llamaindex" in scraper.base_url.lower()


class TestLangChainScraper:
    """Test LangChain scraper."""
    
    def test_initialization(self):
        """Test scraper initializes correctly."""
        scraper = LangChainScraper()
        
        assert scraper.source_name == "LangChain"
        assert "langchain" in scraper.base_url.lower()


class TestHuggingFaceScraper:
    """Test Hugging Face scraper."""
    
    def test_initialization(self):
        """Test scraper initializes correctly."""
        scraper = HuggingFaceScraper()
        
        assert scraper.source_name == "HuggingFace"
        assert "huggingface" in scraper.base_url.lower()


class TestGenericScraper:
    """Test generic scraper."""
    
    def test_initialization_with_custom_config(self):
        """Test scraper initializes with custom config."""
        scraper = GenericScraper(
            source_name="My Blog",
            base_url="https://myblog.com",
            blog_path="/articles",
            max_articles=10,
        )
        
        assert scraper.source_name == "My Blog"
        assert scraper.blog_url == "https://myblog.com/articles"
        assert scraper.max_articles == 10
    
    def test_rss_paths(self):
        """Test that RSS path discovery is configured."""
        assert len(GenericScraper.RSS_PATHS) > 0
        assert "/feed" in GenericScraper.RSS_PATHS


class TestArticleExtraction:
    """Test article content extraction."""
    
    def test_extract_text_content(self):
        """Test text extraction from HTML."""
        from bs4 import BeautifulSoup
        
        html = """
        <html>
        <body>
            <article>
                <h1>Title</h1>
                <p>Paragraph one.</p>
                <script>var x = 1;</script>
                <p>Paragraph two.</p>
            </article>
        </body>
        </html>
        """
        
        scraper = GenericScraper(
            source_name="Test",
            base_url="https://example.com",
        )
        soup = BeautifulSoup(html, "lxml")
        
        content = scraper.extract_text_content(soup, "article")
        
        assert "Title" in content
        assert "Paragraph one" in content
        assert "Paragraph two" in content
        assert "var x" not in content  # Script should be removed
    
    def test_extract_date_from_time_element(self):
        """Test date extraction from time element."""
        from bs4 import BeautifulSoup
        
        html = """
        <html>
        <body>
            <time datetime="2024-01-15T10:00:00Z">January 15, 2024</time>
        </body>
        </html>
        """
        
        scraper = GenericScraper(
            source_name="Test",
            base_url="https://example.com",
        )
        soup = BeautifulSoup(html, "lxml")
        
        date = scraper.extract_date(soup, selectors=["time"])
        
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15
    
    def test_extract_date_from_meta(self):
        """Test date extraction from meta tags."""
        from bs4 import BeautifulSoup
        
        html = """
        <html>
        <head>
            <meta property="article:published_time" content="2024-03-20T12:00:00Z">
        </head>
        <body></body>
        </html>
        """
        
        scraper = GenericScraper(
            source_name="Test",
            base_url="https://example.com",
        )
        soup = BeautifulSoup(html, "lxml")
        
        date = scraper.extract_date(
            soup,
            selectors=[],
            meta_names=["article:published_time"],
        )
        
        assert date is not None
        assert date.year == 2024
        assert date.month == 3


# Integration test markers (require network)
@pytest.mark.integration
@pytest.mark.skip(reason="Requires network access - run manually")
class TestIntegration:
    """Integration tests that make real HTTP requests."""
    
    def test_anthropic_scraper_live(self):
        """Test Anthropic scraper against live site."""
        scraper = AnthropicScraper(max_articles=3)
        urls = scraper.get_article_urls()
        
        assert len(urls) > 0
        assert all(url.startswith("https://") for url in urls)
    
    def test_huggingface_scraper_live(self):
        """Test Hugging Face scraper against live site."""
        scraper = HuggingFaceScraper(max_articles=3)
        urls = scraper.get_article_urls()
        
        assert len(urls) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
