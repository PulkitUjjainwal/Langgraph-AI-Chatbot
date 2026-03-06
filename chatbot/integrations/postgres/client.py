"""
PostgreSQL Database Client with Connection Pooling

Provides async PostgreSQL client using asyncpg with:
- Connection pooling for performance
- Context manager for safe connection handling
- Health checks and monitoring
- Graceful error handling

Usage:
    from chatbot.integrations.postgres.client import pg_client

    # Execute query
    await pg_client.execute("INSERT INTO users (name) VALUES ($1)", "John")

    # Fetch rows
    rows = await pg_client.fetch("SELECT * FROM users WHERE active = $1", True)

    # Fetch single row
    user = await pg_client.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

    # Fetch single value
    count = await pg_client.fetchval("SELECT COUNT(*) FROM users")
"""

import asyncio
from typing import Optional, List, Dict, Any, Union
from contextlib import asynccontextmanager
import asyncpg
from asyncpg.pool import Pool

from chatbot.config.settings import get_settings
from chatbot.config.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()


class PostgreSQLClient:
    """
    Async PostgreSQL client with connection pooling and pgvector support

    Features:
    - Connection pooling (configurable min/max connections)
    - Automatic reconnection on connection loss
    - Health check functionality
    - Query timeout protection
    - Graceful shutdown
    """

    def __init__(self):
        self.pool: Optional[Pool] = None
        self._lock = asyncio.Lock()
        self._initialized = False

    async def connect(self) -> None:
        """
        Initialize connection pool

        Creates an asyncpg connection pool with settings from configuration.
        Safe to call multiple times (idempotent).
        """
        if self.pool is not None:
            logger.debug("PostgreSQL pool already initialized")
            return

        async with self._lock:
            # Double-check after acquiring lock
            if self.pool is not None:
                return

            if not settings.postgres_enabled:
                logger.warning("PostgreSQL is disabled in settings (POSTGRES_ENABLED=false)")
                return

            try:
                logger.info(f"Connecting to PostgreSQL at {settings.postgres_host}:{settings.postgres_port}")

                self.pool = await asyncpg.create_pool(
                    host=settings.postgres_host,
                    port=settings.postgres_port,
                    user=settings.postgres_user,
                    password=settings.postgres_password,
                    database=settings.postgres_database,
                    min_size=settings.postgres_pool_min_size,
                    max_size=settings.postgres_pool_max_size,
                    command_timeout=60,  # 60 second timeout for long queries
                    server_settings={
                        'application_name': 'mi_chatbot',
                        'jit': 'off',  # Disable JIT for faster simple queries
                        'timezone': 'UTC'
                    }
                )

                self._initialized = True
                logger.info(
                    f"✅ PostgreSQL connection pool created "
                    f"(min={settings.postgres_pool_min_size}, max={settings.postgres_pool_max_size})"
                )

                # Test connection
                await self.health_check()

            except asyncpg.InvalidCatalogNameError:
                logger.error(
                    f"❌ Database '{settings.postgres_database}' does not exist. "
                    f"Create it with: CREATE DATABASE {settings.postgres_database};"
                )
                raise
            except asyncpg.InvalidPasswordError:
                logger.error("❌ PostgreSQL authentication failed. Check POSTGRES_PASSWORD in .env")
                raise
            except Exception as e:
                logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
                raise

    async def close(self) -> None:
        """
        Close connection pool gracefully

        Waits for active connections to finish and closes the pool.
        Safe to call multiple times (idempotent).
        """
        if self.pool:
            logger.info("Closing PostgreSQL connection pool...")
            await self.pool.close()
            self.pool = None
            self._initialized = False
            logger.info("PostgreSQL connection pool closed")

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection from the pool

        Usage:
            async with pg_client.acquire() as conn:
                await conn.execute("SELECT 1")
        """
        if self.pool is None:
            await self.connect()

        if self.pool is None:
            raise RuntimeError("PostgreSQL pool not initialized. Check connection settings.")

        async with self.pool.acquire() as connection:
            yield connection

    async def execute(self, query: str, *args, timeout: Optional[float] = None) -> str:
        """
        Execute a query without returning results

        Args:
            query: SQL query with $1, $2, etc. placeholders
            *args: Query parameters
            timeout: Optional query timeout in seconds

        Returns:
            Status string (e.g., "INSERT 0 1", "UPDATE 5")

        Example:
            await pg_client.execute(
                "INSERT INTO users (name, email) VALUES ($1, $2)",
                "John Doe", "john@example.com"
            )
        """
        async with self.acquire() as conn:
            return await conn.execute(query, *args, timeout=timeout)

    async def fetch(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> List[asyncpg.Record]:
        """
        Fetch multiple rows

        Args:
            query: SQL query with $1, $2, etc. placeholders
            *args: Query parameters
            timeout: Optional query timeout in seconds

        Returns:
            List of Record objects (dict-like, supports both row['column'] and row[0])

        Example:
            users = await pg_client.fetch("SELECT * FROM users WHERE active = $1", True)
            for user in users:
                print(user['name'], user['email'])
        """
        async with self.acquire() as conn:
            return await conn.fetch(query, *args, timeout=timeout)

    async def fetchrow(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> Optional[asyncpg.Record]:
        """
        Fetch a single row

        Args:
            query: SQL query with $1, $2, etc. placeholders
            *args: Query parameters
            timeout: Optional query timeout in seconds

        Returns:
            Record object or None if no rows found

        Example:
            user = await pg_client.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
            if user:
                print(user['name'])
        """
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args, timeout=timeout)

    async def fetchval(
        self,
        query: str,
        *args,
        column: int = 0,
        timeout: Optional[float] = None
    ) -> Any:
        """
        Fetch a single value from a single row

        Args:
            query: SQL query with $1, $2, etc. placeholders
            *args: Query parameters
            column: Column index to return (default: 0)
            timeout: Optional query timeout in seconds

        Returns:
            Single value or None if no rows found

        Example:
            count = await pg_client.fetchval("SELECT COUNT(*) FROM users")
            print(f"Total users: {count}")
        """
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args, column=column, timeout=timeout)

    async def executemany(
        self,
        query: str,
        args: List[tuple],
        timeout: Optional[float] = None
    ) -> None:
        """
        Execute a query multiple times with different parameters

        More efficient than executing in a loop.

        Args:
            query: SQL query with $1, $2, etc. placeholders
            args: List of tuples, each containing parameters for one execution
            timeout: Optional query timeout in seconds

        Example:
            await pg_client.executemany(
                "INSERT INTO users (name, email) VALUES ($1, $2)",
                [
                    ("Alice", "alice@example.com"),
                    ("Bob", "bob@example.com"),
                    ("Carol", "carol@example.com")
                ]
            )
        """
        async with self.acquire() as conn:
            await conn.executemany(query, args, timeout=timeout)

    async def transaction(self):
        """
        Start a transaction context

        Usage:
            async with pg_client.transaction():
                await pg_client.execute("UPDATE accounts SET balance = balance - 100 WHERE id = 1")
                await pg_client.execute("UPDATE accounts SET balance = balance + 100 WHERE id = 2")
        """
        conn = await self.pool.acquire()
        try:
            async with conn.transaction():
                yield conn
        finally:
            await self.pool.release(conn)

    async def health_check(self) -> Dict[str, Any]:
        """
        Check database health and connection status

        Returns:
            Dict with health status:
            {
                'status': 'healthy' | 'unhealthy',
                'pool_size': int,
                'pool_available': int,
                'version': str,
                'pgvector_installed': bool
            }
        """
        try:
            if self.pool is None:
                return {
                    'status': 'unhealthy',
                    'error': 'Connection pool not initialized'
                }

            # Test query
            version = await self.fetchval("SELECT version()")

            # Check pgvector extension
            pgvector_installed = await self.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            )

            # Pool stats
            pool_size = self.pool.get_size()
            pool_free = self.pool.get_idle_size()

            health = {
                'status': 'healthy',
                'pool_size': pool_size,
                'pool_available': pool_free,
                'pool_in_use': pool_size - pool_free,
                'version': version.split()[1] if version else 'unknown',
                'pgvector_installed': bool(pgvector_installed)
            }

            if not pgvector_installed:
                health['warning'] = 'pgvector extension not installed (vector search disabled)'
                logger.warning("⚠️  pgvector extension not found. Run: CREATE EXTENSION vector;")

            logger.debug(f"PostgreSQL health check: {health}")
            return health

        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e)
            }

    async def create_partition_if_needed(self, table_name: str, partition_date: Any) -> bool:
        """
        Auto-create monthly partition for conversations or messages

        Args:
            table_name: 'conversations' or 'messages'
            partition_date: Date to create partition for

        Returns:
            True if partition was created, False if already exists
        """
        try:
            if table_name == 'conversations':
                await self.fetchval(
                    "SELECT create_conversation_partition($1)",
                    partition_date
                )
            elif table_name == 'messages':
                await self.fetchval(
                    "SELECT create_message_partition($1)",
                    partition_date
                )
            else:
                raise ValueError(f"Unknown table: {table_name}")

            logger.info(f"✅ Created partition for {table_name} ({partition_date})")
            return True

        except asyncpg.DuplicateTableError:
            # Partition already exists
            return False
        except Exception as e:
            logger.error(f"❌ Failed to create partition: {e}")
            return False

    def is_connected(self) -> bool:
        """Check if client is connected"""
        return self._initialized and self.pool is not None

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics

        Returns:
            Dict with table sizes, row counts, etc.
        """
        try:
            # Get table sizes
            table_sizes = await self.fetch("""
                SELECT
                    tablename,
                    pg_size_pretty(pg_total_relation_size('public.' || tablename)) as size,
                    pg_total_relation_size('public.' || tablename) as bytes
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size('public.' || tablename) DESC
                LIMIT 10
            """)

            # Get total database size
            db_size = await self.fetchval("""
                SELECT pg_size_pretty(pg_database_size(current_database()))
            """)

            # Get row counts for main tables
            counts = {}
            for table in ['users', 'conversations', 'messages', 'embeddings', 'faq']:
                try:
                    count = await self.fetchval(f"SELECT COUNT(*) FROM {table}")
                    counts[table] = count
                except:
                    counts[table] = None

            return {
                'database_size': db_size,
                'table_sizes': [dict(row) for row in table_sizes],
                'row_counts': counts
            }

        except Exception as e:
            logger.error(f"❌ Failed to get stats: {e}")
            return {'error': str(e)}


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

pg_client = PostgreSQLClient()


async def get_postgres_client() -> PostgreSQLClient:
    """
    Dependency injection for FastAPI

    Usage in FastAPI:
        @app.get("/health")
        async def health(pg: PostgreSQLClient = Depends(get_postgres_client)):
            return await pg.health_check()
    """
    if pg_client.pool is None:
        await pg_client.connect()
    return pg_client


# ============================================================================
# STARTUP/SHUTDOWN HANDLERS
# ============================================================================

async def startup_postgres():
    """Call this in FastAPI startup event"""
    await pg_client.connect()


async def shutdown_postgres():
    """Call this in FastAPI shutdown event"""
    await pg_client.close()
