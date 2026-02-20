#!/usr/bin/env python3
"""
Upload locally stored articles to Contextual AI datastore.

Usage:
    python scripts/upload_to_contextual.py              # Upload all
    python scripts/upload_to_contextual.py --source anthropic  # Upload specific source
    python scripts/upload_to_contextual.py --check-status      # Check upload status
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import settings
from src.storage import LocalStorage, ContextualUploader
from src.utils import setup_logging, get_logger


def main():
    parser = argparse.ArgumentParser(
        description="Upload scraped articles to Contextual AI",
    )
    
    parser.add_argument(
        "--source",
        type=str,
        help="Upload articles from a specific source only",
    )
    parser.add_argument(
        "--check-status",
        action="store_true",
        help="Check status of uploaded documents",
    )
    parser.add_argument(
        "--list-documents",
        action="store_true",
        help="List all documents in the datastore",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        help="Override local data directory",
    )
    
    args = parser.parse_args()
    
    # Setup
    setup_logging()
    logger = get_logger("upload")
    
    # Check for API key
    if not settings.contextual_api_key:
        logger.error("CONTEXTUAL_API_KEY environment variable not set")
        print("\nPlease set your Contextual AI API key:")
        print("  export CONTEXTUAL_API_KEY=your_key_here")
        print("\nOr add it to your .env file")
        sys.exit(1)
    
    # Initialize
    data_dir = Path(args.data_dir) if args.data_dir else None
    storage = LocalStorage(base_dir=data_dir)
    uploader = ContextualUploader()
    
    # List documents mode
    if args.list_documents:
        logger.info("Listing documents in datastore...")
        documents = uploader.list_documents()
        
        if not documents:
            print("No documents found (or datastore not configured)")
            return
        
        print(f"\nDocuments in datastore ({len(documents)} total):")
        print("-" * 60)
        for doc in documents:
            status = doc.get("status", "unknown")
            name = doc.get("name", "N/A")
            doc_id = doc.get("id", "N/A")
            print(f"  [{status:12}] {doc_id[:20]}... - {name}")
        print()
        return
    
    # Check status mode
    if args.check_status:
        logger.info("Checking document status...")
        # This would need stored document IDs - for now just list
        documents = uploader.list_documents()
        
        status_counts = {}
        for doc in documents:
            status = doc.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print("\nDocument Status Summary:")
        print("-" * 30)
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")
        print(f"  Total: {len(documents)}")
        print()
        return
    
    # Upload mode
    logger.info("Loading articles for upload...")
    articles = storage.export_for_upload(source=args.source)
    
    if not articles:
        print("No articles found to upload")
        print(f"Data directory: {storage.base_dir}")
        return
    
    logger.info(f"Found {len(articles)} articles to upload")
    
    # Confirm upload
    if len(articles) > 10:
        response = input(f"Upload {len(articles)} articles? [y/N] ")
        if response.lower() != "y":
            print("Cancelled")
            return
    
    # Upload
    results = uploader.upload_batch(articles)
    
    # Print results
    print("\n" + "=" * 50)
    print("UPLOAD SUMMARY")
    print("=" * 50)
    print(f"Total: {results['total']}")
    print(f"Successful: {results['successful']}")
    print(f"Failed: {results['failed']}")
    
    if results['errors']:
        print("\nErrors:")
        for error in results['errors'][:10]:
            if isinstance(error, dict):
                print(f"  - {error.get('article_id', 'Unknown')}: {error.get('url', 'N/A')}")
            else:
                print(f"  - {error}")
    
    # Save results
    results_path = storage.base_dir / "upload_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    main()
