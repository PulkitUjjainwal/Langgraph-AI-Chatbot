"""
Context URL Validator

Extracts URLs from retrieved KB context and validates them before passing to LLM.
Ensures only working URLs (non-404) are shown to users.
"""

import re
from typing import List, Dict, Any, Tuple
from chatbot.utils.url_validator import get_url_validator


class ContextURLValidator:
    """
    Validates URLs in retrieved KB context before passing to LLM

    Prevents:
    1. LLM from seeing and suggesting 404 URLs
    2. Users from being directed to broken pages
    3. Chatbot from blindly creating URLs
    """

    def __init__(self, redis_manager=None):
        """
        Initialize context URL validator

        Args:
            redis_manager: Optional Redis manager for URL caching
        """
        self.url_validator = get_url_validator(redis_manager)

    def extract_urls_from_chunks(self, chunks: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
        """
        Extract URLs from retrieved KB chunks

        Args:
            chunks: List of retrieved chunks from KB

        Returns:
            List of (url, page_title) tuples
        """
        urls = []
        for chunk in chunks:
            url = chunk.get('page_url', '').strip()
            title = chunk.get('page_title', 'Unknown Page')

            if url and url.startswith('http'):
                urls.append((url, title))

        return urls

    async def validate_and_filter_chunks(
        self,
        chunks: List[Dict[str, Any]],
        validate: bool = True
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Validate URLs in chunks and filter out 404s

        Args:
            chunks: List of retrieved KB chunks
            validate: If True, validate URLs (may add latency). If False, only check cache.

        Returns:
            Tuple of (valid_chunks, removed_urls)
            - valid_chunks: Chunks with working URLs
            - removed_urls: List of URLs that were removed (for logging)
        """
        if not chunks:
            return [], []

        valid_chunks = []
        removed_urls = []

        for chunk in chunks:
            url = chunk.get('page_url', '').strip()

            # If no URL, keep chunk (might be general KB content)
            if not url or not url.startswith('http'):
                valid_chunks.append(chunk)
                continue

            # Check cache first (instant)
            is_valid_cached = await self.url_validator.is_valid_cached(url)

            if is_valid_cached is True:
                # URL known to be valid (from cache)
                valid_chunks.append(chunk)
            elif is_valid_cached is False:
                # URL known to be invalid (from cache)
                removed_urls.append(url)
                print(f"[ContextURLValidator] Removed 404 URL (cached): {url[:80]}...")
            else:
                # Not in cache
                if validate:
                    # Validate now (may add ~1 second)
                    is_valid = await self.url_validator.validate_url(url)
                    if is_valid:
                        valid_chunks.append(chunk)
                    else:
                        removed_urls.append(url)
                        print(f"[ContextURLValidator] Removed 404 URL (validated): {url[:80]}...")
                else:
                    # Don't validate (assume valid, validate in background)
                    valid_chunks.append(chunk)
                    # Trigger background validation for future requests
                    await self.url_validator.validate_in_background(url)

        return valid_chunks, removed_urls

    def extract_urls_from_formatted_context(self, formatted_context: str) -> List[str]:
        """
        Extract URLs from formatted context string

        Args:
            formatted_context: Formatted context string with URLs

        Returns:
            List of URLs found in context
        """
        # Pattern: "URL: https://..."
        pattern = r'URL:\s*(https?://[^\s\n]+)'
        urls = re.findall(pattern, formatted_context)
        return urls

    async def remove_404_urls_from_context(
        self,
        formatted_context: str,
        validate: bool = True
    ) -> Tuple[str, List[str]]:
        """
        Remove 404 URLs from formatted context string

        Args:
            formatted_context: Formatted context with URLs
            validate: If True, validate URLs. If False, only check cache.

        Returns:
            Tuple of (cleaned_context, removed_urls)
        """
        urls = self.extract_urls_from_formatted_context(formatted_context)
        removed_urls = []
        cleaned_context = formatted_context

        for url in urls:
            # Check cache first
            is_valid_cached = await self.url_validator.is_valid_cached(url)

            should_remove = False

            if is_valid_cached is False:
                # Known 404 from cache
                should_remove = True
            elif is_valid_cached is None and validate:
                # Not cached, validate now
                is_valid = await self.url_validator.validate_url(url)
                if not is_valid:
                    should_remove = True
            elif is_valid_cached is None and not validate:
                # Not cached, don't validate - validate in background
                await self.url_validator.validate_in_background(url)

            if should_remove:
                # Remove the URL line from context
                pattern = f'URL:\\s*{re.escape(url)}\\n?'
                cleaned_context = re.sub(pattern, '', cleaned_context)
                removed_urls.append(url)
                print(f"[ContextURLValidator] Removed 404 URL from context: {url[:80]}...")

        return cleaned_context, removed_urls

    async def close(self):
        """Close HTTP client"""
        await self.url_validator.close()


# Singleton instance
_context_validator_instance = None


def get_context_url_validator(redis_manager=None):
    """
    Get context URL validator instance (singleton)

    Args:
        redis_manager: Optional Redis manager for URL caching

    Returns:
        ContextURLValidator instance
    """
    global _context_validator_instance
    if _context_validator_instance is None:
        _context_validator_instance = ContextURLValidator(redis_manager)
    return _context_validator_instance
