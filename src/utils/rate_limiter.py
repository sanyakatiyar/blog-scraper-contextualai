"""
Rate limiting utilities for respectful web scraping.
"""

import time
from collections import defaultdict
from datetime import UTC, datetime
from threading import Lock

from config.settings import settings


class RateLimiter:
    """
    Domain-based rate limiter for web scraping.

    Ensures a minimum delay between requests to the same domain.
    """

    def __init__(self, default_delay: float | None = None):
        self.default_delay = default_delay or settings.scrape_delay_seconds
        self._last_request: dict[str, datetime] = defaultdict(
            lambda: datetime.min.replace(tzinfo=UTC)
        )
        self._domain_delays: dict[str, float] = {}
        self._lock = Lock()

    def set_domain_delay(self, domain: str, delay: float) -> None:
        """Set a custom delay for a specific domain."""
        with self._lock:
            self._domain_delays[domain] = delay

    def get_delay(self, domain: str) -> float:
        """Get the configured delay for a domain."""
        return self._domain_delays.get(domain, self.default_delay)

    def wait(self, domain: str) -> float:
        """
        Wait if necessary before making a request to the given domain.

        Returns the time waited in seconds.
        """
        with self._lock:
            now = datetime.now(UTC)
            last_request = self._last_request[domain]
            delay = self.get_delay(domain)

            elapsed = (now - last_request).total_seconds()
            wait_time = max(0, delay - elapsed)

            if wait_time > 0:
                time.sleep(wait_time)

            self._last_request[domain] = datetime.now(UTC)
            return wait_time

    def can_request(self, domain: str) -> bool:
        """Check if a request can be made without waiting."""
        with self._lock:
            now = datetime.now(UTC)
            last_request = self._last_request[domain]
            delay = self.get_delay(domain)

            elapsed = (now - last_request).total_seconds()
            return elapsed >= delay


class RetryHandler:
    """
    Handles retry logic with exponential backoff.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number (0-indexed)."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        return min(delay, self.max_delay)

    def should_retry(self, attempt: int, exception: Exception | None = None) -> bool:
        """Determine if another retry should be attempted."""
        if attempt >= self.max_retries:
            return False

        # Don't retry on certain exceptions
        if exception:
            # Add specific exception handling as needed
            non_retryable = (
                KeyboardInterrupt,
                SystemExit,
            )
            if isinstance(exception, non_retryable):
                return False

        return True

    def wait_for_retry(self, attempt: int) -> float:
        """Wait before the next retry attempt."""
        delay = self.get_delay(attempt)
        time.sleep(delay)
        return delay


# Global rate limiter instance
rate_limiter = RateLimiter()
