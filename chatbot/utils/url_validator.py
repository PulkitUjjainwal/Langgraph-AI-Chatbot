"""
URL Validator with Redis Caching

Validates URLs to prevent showing 404 pages without blocking responses.
Uses background validation + Redis cache for instant lookups.
"""

import asyncio
import httpx
from typing import Optional, Dict
from datetime import timedelta

# In-memory cache for instant lookups (session-level)
_url_cache: Dict[str, bool] = {}


class URLValidator:
    """
    Validates URLs asynchronously with caching

    Strategy:
    1. Check cache first (instant)
    2. Return cached result if available
    3. Validate in background if not cached
    4. Cache result for future use
    """

    def __init__(self, redis_manager=None, cache_ttl_hours: int = 24):
        """
        Initialize URL validator

        Args:
            redis_manager: Optional Redis manager for persistent caching
            cache_ttl_hours: How long to cache URL validation results
        """
        self.redis = redis_manager
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.http_client = httpx.AsyncClient(
            timeout=5.0,  # 5 second timeout
            follow_redirects=True
        )

    def _get_cache_key(self, url: str) -> str:
        """Generate Redis cache key for URL"""
        return f"url_valid:{url}"

    async def is_valid_cached(self, url: str) -> Optional[bool]:
        """
        Check if URL is valid (cached result only - instant)

        Args:
            url: URL to check

        Returns:
            True if valid (cached), False if invalid (cached), None if not cached
        """
        if not url:
            return False

        # Check in-memory cache first (instant)
        if url in _url_cache:
            return _url_cache[url]

        # Check Redis cache if available
        if self.redis:
            cache_key = self._get_cache_key(url)
            cached = await asyncio.to_thread(self.redis.client.get, cache_key)
            if cached is not None:
                is_valid = cached.decode('utf-8') == "1" if isinstance(cached, bytes) else cached == "1"
                _url_cache[url] = is_valid  # Update memory cache
                return is_valid

        # Not cached
        return None

    async def validate_url(self, url: str) -> bool:
        """
        Validate URL by making HTTP request (may take 1-5 seconds)

        OPTIMIZATION: Skip validation for our own generated URLs (marketinsidedata.com)
        to save ~0.5-1 second per request

        Args:
            url: URL to validate

        Returns:
            True if URL is accessible (200-399 status), False otherwise
        """
        if not url:
            return False

        try:
            # Use GET to check response body for "404 page not found" text
            response = await self.http_client.get(url, timeout=5.0)

            # Check status code
            if response.status_code < 200 or response.status_code >= 400:
                await self._cache_result(url, False)
                return False

            # Check for "404 page not found" in response body
            if "404 page not found" in response.text.lower():
                await self._cache_result(url, False)
                return False

            # URL is valid
            await self._cache_result(url, True)
            return True

        except Exception as e:
            print(f"[URLValidator] Failed to validate {url}: {e}")
            # Cache as invalid
            await self._cache_result(url, False)
            return False

    async def _cache_result(self, url: str, is_valid: bool):
        """Cache validation result"""
        # Update in-memory cache
        _url_cache[url] = is_valid

        # Update Redis cache if available
        if self.redis:
            cache_key = self._get_cache_key(url)
            value = "1" if is_valid else "0"
            await asyncio.to_thread(
                self.redis.client.setex,
                cache_key,
                int(self.cache_ttl.total_seconds()),
                value
            )

    async def validate_in_background(self, url: str):
        """
        Validate URL in background (non-blocking)
        Result will be cached for future lookups

        Args:
            url: URL to validate
        """
        asyncio.create_task(self.validate_url(url))

    async def clear_cache(self, url: str = None):
        """
        Clear cached validation result(s)

        Args:
            url: Specific URL to clear. If None, clears all URL caches
        """
        if url:
            # Clear specific URL
            if url in _url_cache:
                del _url_cache[url]
                print(f"[URLValidator] Cleared in-memory cache for: {url[:80]}...")

            if self.redis:
                cache_key = self._get_cache_key(url)
                await asyncio.to_thread(self.redis.client.delete, cache_key)
                print(f"[URLValidator] Cleared Redis cache for: {url[:80]}...")
        else:
            # Clear all URL caches
            _url_cache.clear()
            print(f"[URLValidator] Cleared all in-memory URL caches")

            if self.redis:
                # Delete all url_valid:* keys
                pattern = "url_valid:*"
                cursor = 0
                deleted = 0
                while True:
                    cursor, keys = await asyncio.to_thread(
                        self.redis.client.scan, cursor, match=pattern, count=100
                    )
                    if keys:
                        await asyncio.to_thread(self.redis.client.delete, *keys)
                        deleted += len(keys)
                    if cursor == 0:
                        break
                print(f"[URLValidator] Cleared {deleted} Redis URL caches")

    async def force_revalidate(self, url: str) -> bool:
        """
        Force revalidation of a URL (ignores cache)

        Args:
            url: URL to revalidate

        Returns:
            True if valid, False otherwise
        """
        await self.clear_cache(url)
        return await self.validate_url(url)

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()


# Singleton instance
_validator_instance: Optional[URLValidator] = None


def get_url_validator(redis_manager=None) -> URLValidator:
    """
    Get URL validator instance (singleton)

    Args:
        redis_manager: Optional Redis manager for persistent caching

    Returns:
        URLValidator instance
    """
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = URLValidator(redis_manager)
    return _validator_instance
