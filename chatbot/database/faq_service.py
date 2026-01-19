"""
FAQ Service Module

Provides page-specific suggested questions from MySQL database.
Designed with graceful fallback - if MySQL is unavailable, returns empty list
and the system falls back to LLM-generated questions.
"""

import asyncio
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
import re

# MySQL connector - using aiomysql for async support
try:
    import aiomysql
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    print("[FAQ] Warning: aiomysql not installed. Run: pip install aiomysql")

# Fallback to synchronous mysql-connector if aiomysql not available
if not MYSQL_AVAILABLE:
    try:
        import mysql.connector
        from mysql.connector import pooling
        MYSQL_SYNC_AVAILABLE = True
    except ImportError:
        MYSQL_SYNC_AVAILABLE = False
        print("[FAQ] Warning: mysql-connector-python not installed. FAQ system disabled.")
else:
    MYSQL_SYNC_AVAILABLE = False


class FAQService:
    """
    Service for retrieving page-specific suggested questions from MySQL.

    Features:
    - Connection pooling for performance
    - URL pattern matching to identify pages
    - Graceful fallback if database unavailable
    - Async support with sync fallback
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "chatbot",
        pool_size: int = 5
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size

        self._pool: Optional[aiomysql.Pool] = None
        self._sync_pool = None
        self._initialized = False
        self._available = False

        # Cache for page patterns (refreshed periodically)
        self._page_patterns: List[Dict[str, Any]] = []
        self._patterns_loaded = False

    async def initialize(self) -> bool:
        """
        Initialize database connection pool.
        Returns True if successful, False otherwise.
        """
        if self._initialized:
            return self._available

        self._initialized = True

        # Try async connection first
        if MYSQL_AVAILABLE:
            try:
                self._pool = await aiomysql.create_pool(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    db=self.database,
                    minsize=1,
                    maxsize=self.pool_size,
                    autocommit=True,
                    connect_timeout=5
                )

                # Test connection
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT 1")
                        await cur.fetchone()

                self._available = True
                print(f"[FAQ] ✓ MySQL connection pool initialized (async)")

                # Load page patterns
                await self._load_page_patterns()

                return True

            except Exception as e:
                print(f"[FAQ] MySQL async connection failed: {e}")
                self._pool = None

        # Try sync connection as fallback
        if MYSQL_SYNC_AVAILABLE:
            try:
                self._sync_pool = pooling.MySQLConnectionPool(
                    pool_name="faq_pool",
                    pool_size=self.pool_size,
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    connect_timeout=5
                )

                # Test connection
                conn = self._sync_pool.get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                conn.close()

                self._available = True
                print(f"[FAQ] ✓ MySQL connection pool initialized (sync)")

                # Load page patterns synchronously
                await asyncio.get_event_loop().run_in_executor(
                    None, self._load_page_patterns_sync
                )

                return True

            except Exception as e:
                print(f"[FAQ] MySQL sync connection failed: {e}")
                self._sync_pool = None

        print("[FAQ] ⚠ MySQL unavailable - will use LLM fallback for questions")
        return False

    async def _load_page_patterns(self):
        """Load page URL patterns from database (async)"""
        if not self._pool:
            return

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT id, page_key, url_pattern
                        FROM pages
                        WHERE is_active = TRUE
                        ORDER BY LENGTH(url_pattern) DESC
                    """)
                    self._page_patterns = await cur.fetchall()
                    self._patterns_loaded = True
                    print(f"[FAQ] Loaded {len(self._page_patterns)} page patterns")
        except Exception as e:
            print(f"[FAQ] Error loading page patterns: {e}")

    def _load_page_patterns_sync(self):
        """Load page URL patterns from database (sync)"""
        if not self._sync_pool:
            return

        try:
            conn = self._sync_pool.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, page_key, url_pattern
                FROM pages
                WHERE is_active = TRUE
                ORDER BY LENGTH(url_pattern) DESC
            """)
            self._page_patterns = cursor.fetchall()
            self._patterns_loaded = True
            cursor.close()
            conn.close()
            print(f"[FAQ] Loaded {len(self._page_patterns)} page patterns")
        except Exception as e:
            print(f"[FAQ] Error loading page patterns: {e}")

    def _match_url_to_page(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Match a URL to a page using pattern matching.
        Returns the matched page dict or None.
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
        Get suggested questions for a page based on URL.

        Args:
            url: The page URL to match
            limit: Maximum number of questions to return

        Returns:
            List of question strings, empty list if none found or error
        """
        # Ensure initialized
        if not self._initialized:
            await self.initialize()

        if not self._available:
            return []

        # Match URL to page
        page = self._match_url_to_page(url)
        if not page:
            print(f"[FAQ] No page match for URL: {url[:100]}...")
            return []

        page_id = page.get('id')
        page_key = page.get('page_key', 'unknown')
        print(f"[FAQ] URL matched to page: {page_key} (id={page_id})")

        # Query questions from database
        try:
            if self._pool:
                return await self._get_questions_async(page_id, limit)
            elif self._sync_pool:
                return await asyncio.get_event_loop().run_in_executor(
                    None, self._get_questions_sync, page_id, limit
                )
        except Exception as e:
            print(f"[FAQ] Error fetching questions: {e}")

        return []

    async def _get_questions_async(self, page_id: int, limit: int) -> List[str]:
        """Fetch questions using async connection"""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT question
                    FROM faq
                    WHERE page_id = %s
                      AND question_type = 'suggested'
                      AND is_active = TRUE
                    ORDER BY priority DESC
                    LIMIT %s
                """, (page_id, limit))

                rows = await cur.fetchall()
                questions = [row[0] for row in rows]

                print(f"[FAQ] Retrieved {len(questions)} suggested questions")
                return questions

    def _get_questions_sync(self, page_id: int, limit: int) -> List[str]:
        """Fetch questions using sync connection"""
        conn = self._sync_pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT question
                FROM faq
                WHERE page_id = %s
                  AND question_type = 'suggested'
                  AND is_active = TRUE
                ORDER BY priority DESC
                LIMIT %s
            """, (page_id, limit))

            rows = cursor.fetchall()
            questions = [row[0] for row in rows]
            cursor.close()

            print(f"[FAQ] Retrieved {len(questions)} suggested questions")
            return questions
        finally:
            conn.close()

    async def increment_click_count(self, question: str, page_id: int):
        """Track when a suggested question is clicked (for analytics)"""
        if not self._available:
            return

        try:
            if self._pool:
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("""
                            UPDATE faq
                            SET click_count = click_count + 1
                            WHERE page_id = %s AND question = %s
                        """, (page_id, question))
        except Exception as e:
            # Non-critical, just log
            print(f"[FAQ] Error updating click count: {e}")

    async def close(self):
        """Close database connections"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            print("[FAQ] Connection pool closed")

        if self._sync_pool:
            # Sync pool doesn't need explicit close
            pass

    @property
    def is_available(self) -> bool:
        """Check if FAQ service is available"""
        return self._available


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_faq_service: Optional[FAQService] = None


async def get_faq_service() -> FAQService:
    """Get or create FAQ service singleton"""
    global _faq_service

    if _faq_service is None:
        from chatbot.config.settings import get_settings
        settings = get_settings()

        _faq_service = FAQService(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            pool_size=settings.mysql_pool_size
        )

    return _faq_service


async def init_faq_service() -> Optional[FAQService]:
    """Initialize FAQ service and return it if successful"""
    service = await get_faq_service()
    success = await service.initialize()

    if success:
        return service
    return None
