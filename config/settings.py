"""
Global settings for the blog scraper pipeline.
Uses Pydantic settings for environment variable management.
"""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Contextual AI Configuration
    contextual_api_key: str = Field(
        default="",
        description="Contextual AI API key for datastore access",
    )
    contextual_datastore_id: Optional[str] = Field(
        default=None,
        description="Existing datastore ID to use",
    )
    contextual_datastore_name: str = Field(
        default="context-crew-blogs",
        description="Name for new datastore if ID not provided",
    )

    # Scraping Configuration
    scrape_delay_seconds: float = Field(
        default=2.0,
        description="Delay between requests to same domain",
    )
    max_articles_per_source: int = Field(
        default=50,
        description="Maximum articles to scrape per source",
    )
    request_timeout_seconds: int = Field(
        default=30,
        description="HTTP request timeout",
    )

    # Storage Configuration
    local_data_dir: Path = Field(
        default=Path("./data/raw"),
        description="Directory for local JSON storage",
    )
    enable_html_snapshots: bool = Field(
        default=True,
        description="Store HTML snapshots of scraped pages",
    )

    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )
    log_format: str = Field(
        default="json",
        description="Logging format: json or text",
    )

    # Feature Flags
    dry_run: bool = Field(
        default=False,
        description="Run without uploading to Contextual AI",
    )
    skip_upload: bool = Field(
        default=False,
        description="Skip upload step",
    )
    force_rescrape: bool = Field(
        default=False,
        description="Rescrape even if URL was previously scraped",
    )

    # Project paths
    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent

    @property
    def config_dir(self) -> Path:
        return self.project_root / "config"

    @property
    def sources_config_path(self) -> Path:
        return self.config_dir / "sources.yaml"


# Global settings instance
settings = Settings()
