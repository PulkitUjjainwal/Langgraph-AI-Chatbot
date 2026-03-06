"""
FAQ Service Module - PostgreSQL Edition

Provides page-specific suggested questions from PostgreSQL (or MySQL fallback).
Migrated from MySQL to PostgreSQL with backward compatibility.

Features:
- PostgreSQL as primary database (with pgvector support)
- MySQL fallback during migration
- Full-text search using PostgreSQL's to_tsvector
- Connection pooling for performance
- Graceful degradation if database unavailable
"""

import asyncio
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

from chatbot.integrations.postgres.client import pg_client, get_postgres_client
from chatbot.config.settings import get_settings
from chatbot.config.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()

# MySQL fallback support
MYSQL_AVAILABLE = False
if settings.mysql_enabled:
    try:
        import aiomysql
        MYSQL_AVAILABLE = True
    except ImportError:
        logger.warning("aiomysql not installed. MySQL fallback disabled.")


class FAQService:
    """
    Service for retrieving page-specific suggested questions

    Architecture:
    - Primary: PostgreSQL (with full-text search)
    - Fallback: MySQL (during migration)
    - Graceful degradation if unavailable
    """

    def __init__(self):
        self._postgres_available = False
        self._mysql_pool: Optional[Any] = None
        self._initialized = False

        # Cache for page patterns (refreshed periodically)
        self._page_patterns: List[Dict[str, Any]] = []
        self._patterns_loaded = False

    async def initialize(self) -> bool:
        """
        Initialize database connection.
        Tries PostgreSQL first, falls back to MySQL if needed.

        Returns:
            True if at least one database is available
        """
        if self._initialized:
            return self._postgres_available or (self._mysql_pool is not None)

        self._initialized = True

        # Try PostgreSQL first
        if settings.postgres_enabled:
            try:
                # Ensure PostgreSQL client is connected
                if not pg_client.is_connected():
                    await pg_client.connect()

                # Test connection
                health = await pg_client.health_check()
                if health['status'] == 'healthy':
                    self._postgres_available = True
                    logger.info("✅ FAQ Service connected to PostgreSQL")

                    # Load page patterns
                    await self._load_page_patterns_postgres()
                    return True

            except Exception as e:
                logger.warning(f"PostgreSQL connection failed: {e}")
                self._postgres_available = False

        # Fallback to MySQL if enabled
        if settings.mysql_enabled and MYSQL_AVAILABLE and not self._postgres_available:
            try:
                self._mysql_pool = await aiomysql.create_pool(
                    host=settings.mysql_host,
                    port=settings.mysql_port,
                    user=settings.mysql_user,
                    password=settings.mysql_password,
                    db=settings.mysql_database,
                    minsize=1,
                    maxsize=settings.mysql_pool_size,
                    autocommit=True,
                    connect_timeout=5
                )

                # Test connection
                async with self._mysql_pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT 1")
                        await cur.fetchone()

                logger.info("✅ FAQ Service connected to MySQL (fallback)")

                # Load page patterns
                await self._load_page_patterns_mysql()
                return True

            except Exception as e:
                logger.warning(f"MySQL fallback failed: {e}")
                self._mysql_pool = None

        logger.warning("⚠️  No database available for FAQ - will use LLM fallback")
        return False

    async def _load_page_patterns_postgres(self):
        """Load page URL patterns from PostgreSQL"""
        try:
            rows = await pg_client.fetch("""
                SELECT id, page_key, url_pattern
                FROM pages
                WHERE is_active = TRUE
                ORDER BY LENGTH(url_pattern) DESC
            """)

            self._page_patterns = [dict(row) for row in rows]
            self._patterns_loaded = True
            logger.info(f"Loaded {len(self._page_patterns)} page patterns from PostgreSQL")

        except Exception as e:
            logger.error(f"Error loading page patterns from PostgreSQL: {e}")

    async def _load_page_patterns_mysql(self):
        """Load page URL patterns from MySQL"""
        if not self._mysql_pool:
            return

        try:
            async with self._mysql_pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT id, page_key, url_pattern
                        FROM pages
                        WHERE is_active = TRUE
                        ORDER BY LENGTH(url_pattern) DESC
                    """)
                    self._page_patterns = await cur.fetchall()
                    self._patterns_loaded = True
                    logger.info(f"Loaded {len(self._page_patterns)} page patterns from MySQL")

        except Exception as e:
            logger.error(f"Error loading page patterns from MySQL: {e}")

    def _match_url_to_page(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Match a URL to a page using pattern matching

        Args:
            url: The URL to match

        Returns:
            Matched page dict or None

        Example URL patterns:
            "/" - exact match for home
            "/search-data%" - starts with /search-data
            "%/api%" - contains /api
        """
        if not url or not self._page_patterns:
            return None

        # Normalize URL
        url_lower = url.lower()

        # Try to match against patterns (ordered by specificity - longest first)
        for page in self._page_patterns:
            pattern = page.get('url_pattern', '')
            if not pattern:
                continue

            # Convert SQL LIKE pattern to regex
            # % matches any characters, _ matches single character
            regex_pattern = pattern.lower()
            regex_pattern = regex_pattern.replace('%', '.*')
            regex_pattern = regex_pattern.replace('_', '.')
            regex_pattern = f"^{regex_pattern}$" if not regex_pattern.startswith('.*') else regex_pattern

            try:
                if re.search(regex_pattern, url_lower):
                    return page
            except re.error:
                # Invalid regex, try simple contains match
                simple_pattern = pattern.replace('%', '').replace('_', '')
                if simple_pattern.lower() in url_lower:
                    return page

        return None

    async def get_suggested_questions(
        self,
        url: str,
        limit: int = 5
    ) -> List[str]:
        """
        Get suggested questions for a page based on URL

        Args:
            url: The page URL to match
            limit: Maximum number of questions to return

        Returns:
            List of question strings, empty list if none found

        Example:
            questions = await faq_service.get_suggested_questions("/search-data", limit=5)
            for q in questions:
                print(q)
        """
        # Ensure initialized
        if not self._initialized:
            await self.initialize()

        if not self._postgres_available and not self._mysql_pool:
            logger.debug("FAQ database unavailable")
            return []

        # Match URL to page
        page = self._match_url_to_page(url)
        if not page:
            logger.debug(f"No page match for URL: {url[:100]}...")
            return []

        page_id = page.get('id')
        page_key = page.get('page_key', 'unknown')
        logger.info(f"URL matched to page: {page_key} (id={page_id})")

        # Query questions from database
        try:
            if self._postgres_available:
                return await self._get_questions_postgres(page_id, limit)
            elif self._mysql_pool:
                return await self._get_questions_mysql(page_id, limit)
        except Exception as e:
            logger.error(f"Error fetching questions: {e}", exc_info=True)

        return []

    async def _get_questions_postgres(self, page_id: int, limit: int) -> List[str]:
        """Fetch questions from PostgreSQL"""
        rows = await pg_client.fetch("""
            SELECT question
            FROM faq
            WHERE page_id = $1
              AND question_type = 'suggested'
              AND is_active = TRUE
            ORDER BY priority DESC, click_count DESC
            LIMIT $2
        """, page_id, limit)

        questions = [row['question'] for row in rows]
        logger.info(f"Retrieved {len(questions)} suggested questions from PostgreSQL")
        return questions

    async def _get_questions_mysql(self, page_id: int, limit: int) -> List[str]:
        """Fetch questions from MySQL"""
        async with self._mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT question
                    FROM faq
                    WHERE page_id = %s
                      AND question_type = 'suggested'
                      AND is_active = TRUE
                    ORDER BY priority DESC, click_count DESC
                    LIMIT %s
                """, (page_id, limit))

                rows = await cur.fetchall()
                questions = [row[0] for row in rows]

                logger.info(f"Retrieved {len(questions)} suggested questions from MySQL")
                return questions

    async def search_faq(
        self,
        query: str,
        page_id: Optional[int] = None,
        limit: int = 5
    ) -> List[Dict[str, str]]:
        """
        Search FAQ using full-text search

        Args:
            query: Search query
            page_id: Optional page filter
            limit: Maximum results

        Returns:
            List of FAQ items with question and answer

        Example:
            results = await faq_service.search_faq("export data", limit=5)
            for item in results:
                print(f"Q: {item['question']}")
                print(f"A: {item['answer']}")
        """
        if not self._initialized:
            await self.initialize()

        if not self._postgres_available and not self._mysql_pool:
            return []

        try:
            if self._postgres_available:
                return await self._search_faq_postgres(query, page_id, limit)
            elif self._mysql_pool:
                return await self._search_faq_mysql(query, page_id, limit)
        except Exception as e:
            logger.error(f"FAQ search failed: {e}", exc_info=True)

        return []

    async def _search_faq_postgres(
        self,
        query: str,
        page_id: Optional[int],
        limit: int
    ) -> List[Dict[str, str]]:
        """Search FAQ using PostgreSQL full-text search"""
        where_clause = "WHERE is_active = TRUE"
        params = [query, limit]
        param_idx = 3

        if page_id:
            where_clause += f" AND page_id = ${param_idx}"
            params.insert(1, page_id)
            param_idx += 1

        sql = f"""
            SELECT
                question,
                answer,
                ts_rank(
                    to_tsvector('english', question || ' ' || COALESCE(keywords, '')),
                    plainto_tsquery('english', $1)
                ) as rank
            FROM faq
            {where_clause}
              AND (
                  to_tsvector('english', question || ' ' || COALESCE(keywords, ''))
                  @@ plainto_tsquery('english', $1)
              )
            ORDER BY rank DESC, priority DESC
            LIMIT ${2 if not page_id else 3}
        """

        rows = await pg_client.fetch(sql, *params)

        results = [{'question': row['question'], 'answer': row['answer']} for row in rows]
        logger.info(f"Full-text search found {len(results)} results")
        return results

    async def _search_faq_mysql(
        self,
        query: str,
        page_id: Optional[int],
        limit: int
    ) -> List[Dict[str, str]]:
        """Search FAQ using MySQL MATCH AGAINST"""
        where_clause = "WHERE is_active = TRUE"
        params = [query]

        if page_id:
            where_clause += " AND page_id = %s"
            params.append(page_id)

        params.append(limit)

        async with self._mysql_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(f"""
                    SELECT question, answer
                    FROM faq
                    {where_clause}
                      AND (
                          question LIKE CONCAT('%', %s, '%')
                          OR keywords LIKE CONCAT('%', %s, '%')
                      )
                    ORDER BY priority DESC
                    LIMIT %s
                """, [query, query, *params[1:]])

                rows = await cur.fetchall()
                return [{'question': row['question'], 'answer': row['answer']} for row in rows]

    async def increment_click_count(self, question: str):
        """
        Increment click count for a question

        Args:
            question: The question text that was clicked
        """
        if not self._postgres_available and not self._mysql_pool:
            return

        try:
            if self._postgres_available:
                await pg_client.execute("""
                    UPDATE faq
                    SET click_count = click_count + 1
                    WHERE question = $1
                """, question)
                logger.debug(f"Incremented click count for: {question[:50]}...")

            elif self._mysql_pool:
                async with self._mysql_pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("""
                            UPDATE faq
                            SET click_count = click_count + 1
                            WHERE question = %s
                        """, (question,))
                        logger.debug(f"Incremented click count for: {question[:50]}...")

        except Exception as e:
            logger.error(f"Failed to increment click count: {e}")

    async def close(self):
        """Close database connections"""
        if self._mysql_pool:
            self._mysql_pool.close()
            await self._mysql_pool.wait_closed()
            logger.info("MySQL connection pool closed")

        # PostgreSQL pool is managed globally, don't close it here

    def is_available(self) -> bool:
        """Check if FAQ service is available"""
        return self._postgres_available or (self._mysql_pool is not None)


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_faq_service: Optional[FAQService] = None


async def get_faq_service() -> FAQService:
    """
    Get singleton FAQ service instance

    Usage in FastAPI:
        @app.get("/faq")
        async def get_faqs(faq: FAQService = Depends(get_faq_service)):
            questions = await faq.get_suggested_questions("/", limit=5)
            return {"questions": questions}
    """
    global _faq_service
    if _faq_service is None:
        _faq_service = FAQService()
        await _faq_service.initialize()
    return _faq_service


async def startup_faq():
    """Call this in FastAPI startup event"""
    faq = await get_faq_service()
    if faq.is_available():
        logger.info("✅ FAQ Service initialized")
    else:
        logger.warning("⚠️  FAQ Service unavailable (will use LLM fallback)")


async def shutdown_faq():
    """Call this in FastAPI shutdown event"""
    if _faq_service:
        await _faq_service.close()
