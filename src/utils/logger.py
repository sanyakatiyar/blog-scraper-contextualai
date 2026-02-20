"""
Structured logging configuration for the blog scraper.
"""

import logging
import sys
from datetime import UTC, datetime
from typing import Any

import structlog
from rich.console import Console
from rich.logging import RichHandler

from config.settings import settings


def setup_logging() -> structlog.stdlib.BoundLogger:
    """Configure and return the application logger."""

    # Determine log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure structlog processors
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]

    if settings.log_format == "json":
        # JSON format for production/CI
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        # Rich format for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
        handler = RichHandler(
            console=Console(stderr=True),
            show_time=False,
            show_path=False,
            rich_tracebacks=True,
        )

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        level=log_level,
        handlers=[handler],
        format="%(message)s",
    )

    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    return structlog.get_logger()


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a logger instance with optional name binding."""
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(component=name)
    return logger


class ScrapeMetrics:
    """Track scraping metrics for reporting."""

    def __init__(self):
        self.start_time = datetime.now(UTC)
        self.articles_scraped: dict[str, int] = {}
        self.articles_uploaded: dict[str, int] = {}
        self.errors: list[dict] = []
        self.skipped: dict[str, int] = {}

    def record_scraped(self, source: str, count: int = 1) -> None:
        self.articles_scraped[source] = self.articles_scraped.get(source, 0) + count

    def record_uploaded(self, source: str, count: int = 1) -> None:
        self.articles_uploaded[source] = self.articles_uploaded.get(source, 0) + count

    def record_error(self, source: str, url: str, error: str) -> None:
        self.errors.append(
            {
                "source": source,
                "url": url,
                "error": error,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def record_skipped(self, source: str, count: int = 1) -> None:
        self.skipped[source] = self.skipped.get(source, 0) + count

    def to_dict(self) -> dict:
        end_time = datetime.now(UTC)
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": (end_time - self.start_time).total_seconds(),
            "total_scraped": sum(self.articles_scraped.values()),
            "total_uploaded": sum(self.articles_uploaded.values()),
            "total_errors": len(self.errors),
            "total_skipped": sum(self.skipped.values()),
            "by_source": {
                "scraped": self.articles_scraped,
                "uploaded": self.articles_uploaded,
                "skipped": self.skipped,
            },
            "errors": self.errors[:10],  # Limit errors in report
        }

    def summary(self) -> str:
        """Generate a human-readable summary."""
        d = self.to_dict()
        lines = [
            "=" * 50,
            "SCRAPING SUMMARY",
            "=" * 50,
            f"Duration: {d['duration_seconds']:.1f} seconds",
            f"Total Scraped: {d['total_scraped']}",
            f"Total Uploaded: {d['total_uploaded']}",
            f"Total Skipped: {d['total_skipped']}",
            f"Total Errors: {d['total_errors']}",
            "",
            "By Source:",
        ]

        for source in set(
            list(self.articles_scraped.keys())
            + list(self.articles_uploaded.keys())
            + list(self.skipped.keys())
        ):
            scraped = self.articles_scraped.get(source, 0)
            uploaded = self.articles_uploaded.get(source, 0)
            skipped = self.skipped.get(source, 0)
            lines.append(f"  {source}: scraped={scraped}, uploaded={uploaded}, skipped={skipped}")

        if self.errors:
            lines.extend(["", "Recent Errors:"])
            for err in self.errors[:5]:
                lines.append(f"  [{err['source']}] {err['url'][:50]}...: {err['error'][:100]}")

        lines.append("=" * 50)
        return "\n".join(lines)
