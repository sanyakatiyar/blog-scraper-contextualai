"""
Upload scraped articles to Contextual AI datastore.

Handles document ingestion, status tracking, and error recovery.
"""

import io
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

from config.settings import settings
from src.utils import get_logger

logger = get_logger("storage.contextual")


class ContextualUploader:
    """
    Handles uploading articles to Contextual AI datastore.
    
    Converts articles to a format suitable for ingestion and
    tracks upload status.
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        datastore_id: str | None = None,
    ):
        self.api_key = api_key or settings.contextual_api_key
        self.datastore_id = datastore_id or settings.contextual_datastore_id
        self._client = None
        
        if not self.api_key:
            logger.warning("No Contextual AI API key provided - uploads will be skipped")
    
    @property
    def client(self):
        """Lazy-load the Contextual AI client."""
        if self._client is None:
            try:
                from contextual import ContextualAI
                self._client = ContextualAI(api_key=self.api_key)
            except ImportError:
                logger.error("contextual-client package not installed. Run: pip install contextual-client")
                raise
        return self._client
    
    def ensure_datastore(self) -> str:
        """
        Ensure datastore exists, creating if necessary.
        
        Returns the datastore ID.
        """
        if self.datastore_id:
            logger.info(f"Using existing datastore: {self.datastore_id}")
            return self.datastore_id
        
        # Create new datastore
        datastore_name = settings.contextual_datastore_name
        logger.info(f"Creating new datastore: {datastore_name}")
        
        result = self.client.datastores.create(name=datastore_name)
        self.datastore_id = result.id
        
        logger.info(f"Created datastore with ID: {self.datastore_id}")
        return self.datastore_id
    
    def upload_article(self, article: dict[str, Any]) -> Optional[str]:
        """
        Upload a single article to the datastore.
        
        Converts the article to a text document and ingests it.
        Returns the document ID on success, None on failure.
        """
        if not self.api_key:
            logger.warning("Skipping upload - no API key")
            return None
        
        try:
            # Ensure datastore exists
            datastore_id = self.ensure_datastore()
            
            # Convert article to document format
            document_content = self._article_to_document(article)
            
            # Create a file-like object for upload
            file_content = document_content.encode("utf-8")
            file_obj = io.BytesIO(file_content)
            
            # Generate filename from article ID
            filename = f"{article['id']}.txt"
            
            # Upload to Contextual AI
            result = self.client.datastores.documents.ingest(
                datastore_id=datastore_id,
                file=(filename, file_obj, "text/plain"),
            )
            
            document_id = result.id
            logger.info(f"Uploaded article: {article['title'][:50]}... -> {document_id}")
            
            return document_id
            
        except Exception as e:
            logger.error(f"Failed to upload article {article.get('id')}: {str(e)}")
            return None
    
    def upload_batch(
        self,
        articles: list[dict[str, Any]],
        delay_between: float = 0.5,
    ) -> dict[str, Any]:
        """
        Upload a batch of articles.
        
        Returns a summary of the upload operation.
        """
        results = {
            "total": len(articles),
            "successful": 0,
            "failed": 0,
            "document_ids": [],
            "errors": [],
        }
        
        if not self.api_key:
            logger.warning("Skipping batch upload - no API key")
            results["failed"] = len(articles)
            results["errors"].append("No API key configured")
            return results
        
        for i, article in enumerate(articles):
            logger.info(f"Uploading article {i+1}/{len(articles)}: {article.get('title', 'Unknown')[:40]}...")
            
            doc_id = self.upload_article(article)
            
            if doc_id:
                results["successful"] += 1
                results["document_ids"].append({
                    "article_id": article.get("id"),
                    "document_id": doc_id,
                })
            else:
                results["failed"] += 1
                results["errors"].append({
                    "article_id": article.get("id"),
                    "url": article.get("url"),
                })
            
            # Rate limiting
            if i < len(articles) - 1:
                time.sleep(delay_between)
        
        logger.info(
            f"Batch upload complete: {results['successful']}/{results['total']} successful"
        )
        
        return results
    
    def _article_to_document(self, article: dict[str, Any]) -> str:
        """
        Convert an article dict to a text document for ingestion.
        
        Includes metadata as structured headers for better retrieval.
        """
        parts = []
        
        # Title
        parts.append(f"# {article.get('title', 'Untitled')}")
        parts.append("")
        
        # Metadata section
        parts.append("## Metadata")
        parts.append(f"- Source: {article.get('source_name', article.get('source', 'Unknown'))}")
        parts.append(f"- URL: {article.get('url', 'N/A')}")
        parts.append(f"- Author: {article.get('author', 'Unknown')}")
        
        if article.get("published_date"):
            parts.append(f"- Published: {article['published_date']}")
        
        if article.get("tags"):
            parts.append(f"- Tags: {', '.join(article['tags'])}")
        
        parts.append(f"- Word Count: {article.get('word_count', 'N/A')}")
        parts.append("")
        
        # Summary
        if article.get("summary"):
            parts.append("## Summary")
            parts.append(article["summary"])
            parts.append("")
        
        # Main content
        parts.append("## Content")
        parts.append(article.get("content_text", ""))
        
        return "\n".join(parts)
    
    def check_document_status(self, document_id: str) -> dict[str, Any]:
        """Check the processing status of an uploaded document."""
        if not self.api_key or not self.datastore_id:
            return {"status": "unknown", "error": "Not configured"}
        
        try:
            metadata = self.client.datastores.documents.metadata(
                datastore_id=self.datastore_id,
                document_id=document_id,
            )
            return {
                "status": metadata.ingestion_job_status,
                "document_id": document_id,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "document_id": document_id,
            }
    
    def list_documents(self) -> list[dict[str, Any]]:
        """List all documents in the datastore."""
        if not self.api_key or not self.datastore_id:
            return []
        
        try:
            documents = []
            for doc in self.client.datastores.documents.list(datastore_id=self.datastore_id):
                documents.append({
                    "id": doc.id,
                    "name": getattr(doc, "name", None),
                    "status": getattr(doc, "ingestion_job_status", None),
                })
            return documents
        except Exception as e:
            logger.error(f"Failed to list documents: {str(e)}")
            return []
