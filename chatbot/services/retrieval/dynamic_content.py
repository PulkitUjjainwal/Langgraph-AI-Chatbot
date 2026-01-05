"""
Production-Grade Dynamic Content Manager

Manages dynamic content fetching and embedding generation:
- Fetches content from URLs using platform APIs (Export Genius, Marketinside)
- Supports both company and country pages
- Generates embeddings for dynamic content
- Caches content and embeddings in Redis
- Parallel embedding processing for performance
- API-only mode (web scraping disabled)
"""

import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import faiss

from chatbot.config.settings import get_settings
from chatbot.config.logging_config import get_logger
from chatbot.integrations.redis.client import RedisMemoryManager
from chatbot.services.llm.ollama_client import get_ollama_client
from chatbot.utils.exceptions import DynamicContentError, EmbeddingError

logger = get_logger(__name__)


class DynamicContentManager:
    """Manages dynamic content fetching and embedding generation per session"""

    def __init__(
        self,
        redis_manager: RedisMemoryManager,
        settings=None,
        ollama_client=None
    ):
        """
        Initialize Dynamic Content Manager

        Args:
            redis_manager: Redis memory manager instance
            settings: Settings instance (for dependency injection)
            ollama_client: Ollama client instance (for dependency injection)
        """
        self.redis = redis_manager
        self.settings = settings or get_settings()
        self.ollama_client = ollama_client or get_ollama_client()

        self.content_cache: Dict[str, str] = {}
        self.max_cache_size = 25  # Reduced from 50 to save ~2.5MB RAM

        # Try to import optional integrations
        self._setup_integrations()

    def _setup_integrations(self):
        """Setup optional integrations (API clients only - web scraping disabled)"""
        # Web Scraper - DISABLED (only use API data)
        self.scraping_available = False
        logger.info("Web scraping DISABLED - using API data only")

        # PRODUCTION-GRADE UNIFIED API CLIENT
        # Handles: Export Genius + Marketinside
        # Page Types: Company (8 endpoints), Country (9 endpoints), Search Data (6+ endpoints)
        # Features: Concurrent calls, retry logic, error handling, caching
        try:
            from chatbot.integrations.apis.unified_integration import (
                fetch_and_format_content,
                is_company_url,
                is_country_url,
                is_search_data_url,
                get_platform,
                get_page_type
            )
            self.fetch_unified_content = fetch_and_format_content
            self.is_company_url = is_company_url
            self.is_country_url = is_country_url
            self.is_search_data_url = is_search_data_url
            self.get_platform = get_platform
            self.get_page_type = get_page_type
            self.unified_api_available = True
            logger.info("✓ Production-Grade Unified API Client loaded")
            logger.info("  - Export Genius: Company, Country, Search Data")
            logger.info("  - Marketinside: Company (8 endpoints), Country (9 endpoints), Search Data (6+ endpoints)")
        except ImportError as e:
            self.unified_api_available = False
            logger.error(f"✗ Unified API Client not available: {e}")
            logger.info("  Falling back to legacy clients...")

        # Legacy API Clients (FALLBACK ONLY)
        # These will be removed after unified client is fully tested
        try:
            from chatbot.integrations.apis.export_genius import (
                ExportGeniusAPIClient,
                fetch_company_data_from_url as fetch_eg_data
            )
            self.ExportGeniusAPIClient = ExportGeniusAPIClient
            self.fetch_eg_company_data = fetch_eg_data
            self.eg_api_available = True
            logger.info("(Legacy Fallback) Export Genius API available")
        except ImportError:
            self.eg_api_available = False

        try:
            from chatbot.integrations.apis.marketinside import (
                MarketinsideAPIClient,
                fetch_company_data_from_url as fetch_mi_company_data,
                fetch_country_data_from_url as fetch_mi_country_data
            )
            self.MarketinsideAPIClient = MarketinsideAPIClient
            self.fetch_mi_company_data = fetch_mi_company_data
            self.fetch_mi_country_data = fetch_mi_country_data
            self.mi_api_available = True
            logger.info("(Legacy Fallback) Marketinside API available")
        except ImportError:
            self.mi_api_available = False

    async def fetch_content(self, url: str, session_id: str = "") -> str:
        """
        Fetch content from URL with caching

        PRODUCTION-GRADE UNIFIED APPROACH:
        1. Check cache
        2. Use Production-Grade Unified API Client (handles all page types)
        3. Fallback to legacy clients only if unified client fails

        Supported via Unified Client:
        - Company pages: 8 concurrent API calls (overview + 7 parallel)
        - Country pages: 9 concurrent API calls (all parallel)
        - Search Data pages: 6+ concurrent API calls (all parallel)

        Args:
            url: URL to fetch content from
            session_id: Session identifier (for logging)

        Returns:
            Formatted content as string

        Raises:
            DynamicContentError: If content fetching fails
        """
        # =====================================================================
        # STEP 1: Check cache
        # =====================================================================
        if url in self.content_cache:
            logger.debug(f"⚡ Cache hit for {url}")
            return self.content_cache[url]

        content = ""

        # =====================================================================
        # STEP 2: Use Production-Grade Unified API Client
        # =====================================================================
        if self.unified_api_available:
            try:
                logger.info(f"[UNIFIED] Fetching: {url}")

                # Fetch and format content (auto-detects everything)
                formatted_text, platform, page_type = await self.fetch_unified_content(url)

                if formatted_text and not formatted_text.startswith("Error"):
                    content = formatted_text
                    logger.info(
                        f"✓ [UNIFIED] Success: {page_type.value} from {platform.value} "
                        f"({len(content):,} chars)"
                    )
                else:
                    logger.warning(f"[UNIFIED] Returned error or empty: {formatted_text[:100]}")

            except Exception as e:
                logger.error(f"✗ [UNIFIED] Exception: {e}", exc_info=True)
                logger.info("[UNIFIED] Attempting legacy fallback...")

        # =====================================================================
        # STEP 3: Legacy Fallback (only if unified failed)
        # =====================================================================
        if not content:
            logger.warning("[LEGACY] Unified client failed, trying legacy clients")

            # Try Export Genius
            if self.eg_api_available and self.ExportGeniusAPIClient.is_company_url(url):
                try:
                    logger.info("[LEGACY] Attempting Export Genius")
                    formatted_data = await self.fetch_eg_company_data(url)
                    if formatted_data:
                        content = "[Company Data from Export Genius API]\n\n" + formatted_data
                        logger.info("✓ [LEGACY] Export Genius succeeded")
                except Exception as e:
                    logger.error(f"✗ [LEGACY] Export Genius failed: {e}")

            # Try Marketinside company
            elif self.mi_api_available and self.MarketinsideAPIClient.is_company_url(url):
                try:
                    logger.info("[LEGACY] Attempting Marketinside company")
                    formatted_data = await self.fetch_mi_company_data(url)
                    if formatted_data:
                        content = "[Company Data from Marketinside API]\n\n" + formatted_data
                        logger.info("✓ [LEGACY] Marketinside company succeeded")
                except Exception as e:
                    logger.error(f"✗ [LEGACY] Marketinside company failed: {e}")

            # Try Marketinside country
            elif self.mi_api_available and self.MarketinsideAPIClient.is_country_url(url):
                try:
                    logger.info("[LEGACY] Attempting Marketinside country")
                    data_type = "import"  # TODO: Auto-detect from URL
                    formatted_data = await self.fetch_mi_country_data(url, data_type=data_type)
                    if formatted_data:
                        content = f"[Country Data - {data_type.upper()}]\n\n" + formatted_data
                        logger.info(f"✓ [LEGACY] Marketinside country succeeded ({data_type})")
                except Exception as e:
                    logger.error(f"✗ [LEGACY] Marketinside country failed: {e}")

            else:
                logger.error("[LEGACY] No legacy client matched this URL")

        # =====================================================================
        # STEP 4: Cache and return
        # =====================================================================
        if content:
            self._add_to_cache(url, content)
            logger.info(f"✓ Cached successfully ({len(self.content_cache)}/{self.max_cache_size})")
            return content
        else:
            error_msg = f"All fetching methods failed for {url}"
            logger.error(f"✗ {error_msg}")
            raise DynamicContentError(error_msg)

    def _add_to_cache(self, key: str, value: str):
        """
        Add content to cache with size limit (LRU eviction)

        Args:
            key: Cache key (usually URL)
            value: Content to cache
        """
        if len(self.content_cache) >= self.max_cache_size:
            # Remove oldest entry (first item)
            self.content_cache.pop(next(iter(self.content_cache)))

        self.content_cache[key] = value
        logger.debug(f"Cached content (cache size: {len(self.content_cache)})")

    def _chunk_content(
        self,
        content: str,
        chunk_size: int = 800,
        overlap: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Chunk content into smaller pieces for embedding

        Args:
            content: Text content to chunk
            chunk_size: Size of each chunk in words
            overlap: Number of overlapping words between chunks

        Returns:
            List of chunk dictionaries
        """
        words = content.split()
        chunks = []

        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)

            chunks.append({
                'chunk_id': i // (chunk_size - overlap),
                'chunk_text': chunk_text,
                'word_count': len(chunk_words)
            })

        return chunks

    async def generate_and_store_embeddings(
        self,
        content: str,
        url: str,
        session_id: str
    ):
        """
        Generate embeddings for dynamic content and store in Redis (PARALLEL PROCESSING)

        Uses parallel processing with concurrency limits to generate embeddings quickly
        while respecting API rate limits.

        Args:
            content: Raw text content
            url: Source URL
            session_id: Session identifier

        Raises:
            EmbeddingError: If embedding generation fails
            TimeoutError: If embedding generation times out
        """
        embed_start = time.time()
        logger.info(
            f"Generating embeddings for session: {session_id}",
            extra={"session_id": session_id, "url": url}
        )

        # 1. Chunk content
        chunks = self._chunk_content(content, chunk_size=800, overlap=100)

        if not chunks:
            logger.warning("No chunks generated from content")
            return

        # Extract chunk texts
        chunk_texts = [chunk['chunk_text'] for chunk in chunks]
        total_chars = sum(len(text) for text in chunk_texts)

        # Hard limit on chunks to prevent massive processing
        MAX_TOTAL_CHUNKS = 15
        if len(chunk_texts) > MAX_TOTAL_CHUNKS:
            logger.info(
                f"Truncating {len(chunk_texts)} chunks to {MAX_TOTAL_CHUNKS} for performance"
            )
            chunk_texts = chunk_texts[:MAX_TOTAL_CHUNKS]
            chunks = chunks[:MAX_TOTAL_CHUNKS]
            total_chars = sum(len(text) for text in chunk_texts)

        logger.info(
            f"Processing {len(chunk_texts)} chunks ({total_chars:,} chars) in PARALLEL..."
        )

        try:
            # PARALLEL PROCESSING with concurrency limit
            MAX_CONCURRENT = 5  # Process 5 chunks simultaneously

            async def embed_single_chunk(chunk_text: str, chunk_idx: int) -> list:
                """Embed a single chunk with error handling"""
                try:
                    response = await asyncio.to_thread(
                        self.ollama_client.embeddings,
                        model=self.settings.embedding_model,
                        prompt=chunk_text
                    )
                    embeddings = response.get('embeddings')
                    if not embeddings or len(embeddings) == 0:
                        raise ValueError(f"No embeddings in response for chunk {chunk_idx}")
                    return embeddings[0]
                except Exception as e:
                    logger.error(f"Chunk {chunk_idx} failed: {e}")
                    raise

            # Use semaphore to limit concurrent requests
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

            async def embed_with_limit(chunk_text: str, chunk_idx: int) -> list:
                """Embed with concurrency limit"""
                async with semaphore:
                    return await embed_single_chunk(chunk_text, chunk_idx)

            # Process all chunks in parallel (with concurrency limit)
            logger.debug(
                f"Launching {len(chunk_texts)} embedding tasks ({MAX_CONCURRENT} concurrent)"
            )

            embedding_tasks = [
                embed_with_limit(chunk_text, i + 1)
                for i, chunk_text in enumerate(chunk_texts)
            ]

            # Add timeout to prevent hanging
            embeddings_list = await asyncio.wait_for(
                asyncio.gather(*embedding_tasks),
                timeout=30.0  # 30 second timeout
            )

            embed_elapsed = time.time() - embed_start
            logger.info(
                f"Generated {len(embeddings_list)} embeddings in {embed_elapsed:.2f}s "
                f"({len(embeddings_list)/embed_elapsed:.1f} emb/s) - PARALLEL MODE"
            )

        except asyncio.TimeoutError:
            embed_elapsed = time.time() - embed_start
            logger.error(
                f"Embedding generation TIMEOUT after {embed_elapsed:.1f}s",
                extra={"chunks": len(chunk_texts), "chars": total_chars}
            )
            raise TimeoutError(f"Embedding generation timed out after {embed_elapsed:.1f}s")

        except Exception as e:
            embed_elapsed = time.time() - embed_start
            logger.error(
                f"Parallel embedding failed after {embed_elapsed:.1f}s: {type(e).__name__}: {str(e)}",
                extra={"chunks": len(chunk_texts), "chars": total_chars},
                exc_info=True
            )
            raise EmbeddingError(f"Embedding generation failed: {str(e)}") from e

        # Normalize embeddings
        embeddings_array = np.array(embeddings_list).astype('float32')
        faiss.normalize_L2(embeddings_array)

        # Store in Redis (with full content)
        self.redis.save_embeddings(
            session_id=session_id,
            dynamic_url=url,
            embeddings=embeddings_array,
            chunks=chunks,
            full_content=content
        )

        logger.info(
            f"Embeddings stored: {len(chunks)} chunks, {embeddings_array.shape}",
            extra={"session_id": session_id, "url": url}
        )

    async def get_embeddings_from_redis(
        self,
        url: str,
        session_id: str
    ) -> Optional[tuple]:
        """
        Get embeddings from Redis cache

        Args:
            url: URL to fetch embeddings for
            session_id: Session identifier

        Returns:
            Tuple of (embeddings, chunks, full_content) or None if not found
        """
        return self.redis.get_embeddings(session_id, url)

    def clear_cache(self):
        """Clear the in-memory content cache"""
        self.content_cache.clear()
        logger.info("Content cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics

        Returns:
            Dict with stats
        """
        return {
            "content_cache_size": len(self.content_cache),
            "max_cache_size": self.max_cache_size,
            "scraping_available": self.scraping_available,
            "export_genius_api_available": self.eg_api_available,
            "marketinside_api_available": self.mi_api_available
        }
