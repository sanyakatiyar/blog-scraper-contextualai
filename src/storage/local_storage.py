"""
Local file storage for scraped articles.

Stores articles as JSON files for local testing and backup.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import settings
from src.utils import get_logger

logger = get_logger("storage.local")


class LocalStorage:
    """
    Local JSON file storage for scraped articles.
    
    Organizes files by source and date for easy browsing.
    """
    
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or settings.local_data_dir
        self.base_dir = Path(self.base_dir)
        self._ensure_dirs()
    
    def _ensure_dirs(self) -> None:
        """Ensure storage directories exist."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "articles").mkdir(exist_ok=True)
        (self.base_dir / "metadata").mkdir(exist_ok=True)
        (self.base_dir / "html_snapshots").mkdir(exist_ok=True)
    
    def save_article(self, article: dict[str, Any]) -> Path:
        """
        Save a single article to local storage.
        
        Returns the path to the saved file.
        """
        source = article.get("source", "unknown")
        article_id = article.get("id", "unknown")
        
        # Create source directory
        source_dir = self.base_dir / "articles" / source
        source_dir.mkdir(parents=True, exist_ok=True)
        
        # Save article JSON
        article_path = source_dir / f"{article_id}.json"
        with open(article_path, "w", encoding="utf-8") as f:
            json.dump(article, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Saved article to {article_path}")
        
        # Save HTML snapshot if present
        if article.get("content_html"):
            html_dir = self.base_dir / "html_snapshots" / source
            html_dir.mkdir(parents=True, exist_ok=True)
            html_path = html_dir / f"{article_id}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(article["content_html"])
        
        return article_path
    
    def save_batch(self, articles: list[dict[str, Any]], source: str) -> list[Path]:
        """
        Save a batch of articles.
        
        Also updates the source metadata file.
        """
        paths = []
        
        for article in articles:
            path = self.save_article(article)
            paths.append(path)
        
        # Update source metadata
        self._update_source_metadata(source, articles)
        
        return paths
    
    def _update_source_metadata(self, source: str, articles: list[dict[str, Any]]) -> None:
        """Update metadata file for a source."""
        metadata_path = self.base_dir / "metadata" / f"{source}_metadata.json"
        
        # Load existing metadata
        existing = {}
        if metadata_path.exists():
            with open(metadata_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        
        # Update with new articles
        now = datetime.now(timezone.utc).isoformat()
        existing["last_updated"] = now
        existing["source"] = source
        
        if "articles" not in existing:
            existing["articles"] = {}
        
        for article in articles:
            article_id = article.get("id")
            existing["articles"][article_id] = {
                "url": article.get("url"),
                "title": article.get("title"),
                "published_date": article.get("published_date"),
                "scraped_at": article.get("scraped_at"),
            }
        
        existing["total_articles"] = len(existing["articles"])
        
        # Save metadata
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
    
    def load_article(self, source: str, article_id: str) -> dict[str, Any] | None:
        """Load a single article by source and ID."""
        article_path = self.base_dir / "articles" / source / f"{article_id}.json"
        
        if not article_path.exists():
            return None
        
        with open(article_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def list_articles(self, source: str | None = None) -> list[dict[str, Any]]:
        """
        List all articles, optionally filtered by source.
        
        Returns lightweight metadata, not full content.
        """
        articles = []
        
        if source:
            sources = [source]
        else:
            sources = [d.name for d in (self.base_dir / "articles").iterdir() if d.is_dir()]
        
        for src in sources:
            metadata_path = self.base_dir / "metadata" / f"{src}_metadata.json"
            if metadata_path.exists():
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                    for article_id, info in metadata.get("articles", {}).items():
                        articles.append({
                            "id": article_id,
                            "source": src,
                            **info,
                        })
        
        return articles
    
    def get_scraped_urls(self, source: str | None = None) -> set[str]:
        """Get set of already-scraped URLs to avoid duplicates."""
        urls = set()

        articles = self.list_articles(source)
        for article in articles:
            if article.get("url"):
                urls.add(article["url"])

        return urls

    # ------------------------------------------------------------------
    # Persistent URL registry (survives across CI runs)
    # ------------------------------------------------------------------

    def load_url_registry(self, registry_path: Path) -> dict[str, set[str]]:
        """
        Load the persistent scraped-URL registry from a JSON file.

        Returns a dict mapping source_id -> set of scraped URLs.
        """
        if not registry_path.exists():
            return {}
        with open(registry_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {source: set(urls) for source, urls in raw.items()}

    def save_url_registry(
        self, registry_path: Path, registry: dict[str, set[str]]
    ) -> None:
        """
        Save the persistent scraped-URL registry to a JSON file.

        Converts sets to sorted lists for stable diffs in git.
        """
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {source: sorted(urls) for source, urls in registry.items()}
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        logger.debug(f"Saved URL registry to {registry_path}")

    def clear_source(self, source: str) -> int:
        """
        Clear all articles for a source.
        
        Returns the number of articles deleted.
        """
        count = 0
        
        # Remove article files
        source_dir = self.base_dir / "articles" / source
        if source_dir.exists():
            for f in source_dir.glob("*.json"):
                f.unlink()
                count += 1
            source_dir.rmdir()
        
        # Remove HTML snapshots
        html_dir = self.base_dir / "html_snapshots" / source
        if html_dir.exists():
            for f in html_dir.glob("*.html"):
                f.unlink()
            html_dir.rmdir()
        
        # Remove metadata
        metadata_path = self.base_dir / "metadata" / f"{source}_metadata.json"
        if metadata_path.exists():
            metadata_path.unlink()
        
        logger.info(f"Cleared {count} articles for source: {source}")
        return count
    
    def export_for_upload(self, source: str | None = None) -> list[dict[str, Any]]:
        """
        Export articles in a format ready for Contextual AI upload.
        
        Returns full article data (not just metadata).
        """
        articles = []
        
        if source:
            sources = [source]
        else:
            articles_dir = self.base_dir / "articles"
            if articles_dir.exists():
                sources = [d.name for d in articles_dir.iterdir() if d.is_dir()]
            else:
                sources = []
        
        for src in sources:
            source_dir = self.base_dir / "articles" / src
            if source_dir.exists():
                for article_file in source_dir.glob("*.json"):
                    with open(article_file, "r", encoding="utf-8") as f:
                        article = json.load(f)
                        articles.append(article)
        
        return articles
