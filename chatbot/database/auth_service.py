"""
Authentication Database Service

Handles database operations for users and refresh tokens.
"""

import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import logging

try:
    import aiomysql
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    print("[Auth] Warning: aiomysql not installed. Run: pip install aiomysql")

logger = logging.getLogger(__name__)


class AuthDatabaseService:
    """
    Database service for authentication operations.

    Features:
    - Async MySQL operations with connection pooling
    - User CRUD operations
    - Refresh token management
    - Last login tracking
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
        self._initialized = False
        self._available = False

    async def initialize(self) -> bool:
        """
        Initialize database connection pool.
        Returns True if successful, False otherwise.
        """
        if self._initialized:
            return self._available

        self._initialized = True

        if not MYSQL_AVAILABLE:
            logger.error("[Auth] MySQL driver not available")
            return False

        try:
            self._pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                minsize=1,
                maxsize=self.pool_size,
                autocommit=True
            )
            self._available = True
            logger.info(f"[Auth] Database connection pool initialized (size={self.pool_size})")
            return True

        except Exception as e:
            logger.error(f"[Auth] Failed to initialize database: {e}")
            self._available = False
            return False

    async def close(self):
        """Close database connection pool"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            logger.info("[Auth] Database connection pool closed")

    # ============================================================================
    # USER OPERATIONS
    # ============================================================================

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email address"""
        if not self._available:
            logger.error("[Auth] Database not available")
            return None

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        """
                        SELECT id, username, email, password_hash, full_name,
                               role, is_active, created_at, updated_at, last_login_at
                        FROM users
                        WHERE email = %s
                        """,
                        (email,)
                    )
                    result = await cursor.fetchone()
                    return result

        except Exception as e:
            logger.error(f"[Auth] Error getting user by email: {e}")
            return None

    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        if not self._available:
            logger.error("[Auth] Database not available")
            return None

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        """
                        SELECT id, username, email, password_hash, full_name,
                               role, is_active, created_at, updated_at, last_login_at
                        FROM users
                        WHERE id = %s
                        """,
                        (user_id,)
                    )
                    result = await cursor.fetchone()
                    return result

        except Exception as e:
            logger.error(f"[Auth] Error getting user by ID: {e}")
            return None

    async def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        full_name: str,
        role: str = "user"
    ) -> Optional[int]:
        """
        Create a new user.
        Returns user ID if successful, None otherwise.
        """
        if not self._available:
            logger.error("[Auth] Database not available")
            return None

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        INSERT INTO users (username, email, password_hash, full_name, role, is_active)
                        VALUES (%s, %s, %s, %s, %s, TRUE)
                        """,
                        (username, email, password_hash, full_name, role)
                    )
                    user_id = cursor.lastrowid
                    logger.info(f"[Auth] Created user: {email} (ID: {user_id})")
                    return user_id

        except Exception as e:
            logger.error(f"[Auth] Error creating user: {e}")
            return None

    async def update_user(
        self,
        user_id: int,
        full_name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """
        Update user information.
        Returns True if successful, False otherwise.
        """
        if not self._available:
            logger.error("[Auth] Database not available")
            return False

        # Build dynamic UPDATE query
        updates = []
        params = []

        if full_name is not None:
            updates.append("full_name = %s")
            params.append(full_name)

        if role is not None:
            updates.append("role = %s")
            params.append(role)

        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)

        if not updates:
            return True  # No updates to make

        params.append(user_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    logger.info(f"[Auth] Updated user ID: {user_id}")
                    return True

        except Exception as e:
            logger.error(f"[Auth] Error updating user: {e}")
            return False

    async def update_last_login(self, user_id: int) -> bool:
        """Update user's last login timestamp"""
        if not self._available:
            return False

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        "UPDATE users SET last_login_at = NOW() WHERE id = %s",
                        (user_id,)
                    )
                    return True

        except Exception as e:
            logger.error(f"[Auth] Error updating last login: {e}")
            return False

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        role: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get paginated list of users.
        Returns dict with users list and pagination info.
        """
        if not self._available:
            logger.error("[Auth] Database not available")
            return {"users": [], "total": 0, "page": page, "page_size": page_size}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    # Build WHERE clause
                    where_clause = ""
                    params = []

                    if role:
                        where_clause = "WHERE role = %s"
                        params.append(role)

                    # Get total count
                    count_query = f"SELECT COUNT(*) as total FROM users {where_clause}"
                    await cursor.execute(count_query, params)
                    count_result = await cursor.fetchone()
                    total = count_result["total"]

                    # Get paginated users
                    offset = (page - 1) * page_size
                    users_query = f"""
                        SELECT id, username, email, full_name, role, is_active,
                               created_at, updated_at, last_login_at
                        FROM users
                        {where_clause}
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                    """
                    params.extend([page_size, offset])
                    await cursor.execute(users_query, params)
                    users = await cursor.fetchall()

                    return {
                        "users": users,
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                        "total_pages": (total + page_size - 1) // page_size
                    }

        except Exception as e:
            logger.error(f"[Auth] Error listing users: {e}")
            return {"users": [], "total": 0, "page": page, "page_size": page_size}

    async def delete_user(self, user_id: int) -> bool:
        """
        Soft delete user by setting is_active = False.
        Returns True if successful, False otherwise.
        """
        return await self.update_user(user_id, is_active=False)

    # ============================================================================
    # REFRESH TOKEN OPERATIONS
    # ============================================================================

    async def store_refresh_token(
        self,
        user_id: int,
        token: str,
        expires_days: int = 30
    ) -> bool:
        """
        Store a refresh token in the database.
        Token is hashed before storage for security.
        """
        if not self._available:
            return False

        # Hash the token before storing
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = datetime.utcnow() + timedelta(days=expires_days)

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
                        VALUES (%s, %s, %s)
                        """,
                        (user_id, token_hash, expires_at)
                    )
                    logger.info(f"[Auth] Stored refresh token for user ID: {user_id}")
                    return True

        except Exception as e:
            logger.error(f"[Auth] Error storing refresh token: {e}")
            return False

    async def verify_refresh_token(self, token: str) -> Optional[int]:
        """
        Verify a refresh token and return user ID if valid.
        Returns None if token is invalid, expired, or revoked.
        """
        if not self._available:
            return None

        token_hash = hashlib.sha256(token.encode()).hexdigest()

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        """
                        SELECT user_id, expires_at, is_revoked
                        FROM refresh_tokens
                        WHERE token_hash = %s
                        """,
                        (token_hash,)
                    )
                    result = await cursor.fetchone()

                    if not result:
                        return None

                    if result["is_revoked"]:
                        logger.warning("[Auth] Attempted to use revoked token")
                        return None

                    if result["expires_at"] < datetime.utcnow():
                        logger.warning("[Auth] Attempted to use expired token")
                        return None

                    return result["user_id"]

        except Exception as e:
            logger.error(f"[Auth] Error verifying refresh token: {e}")
            return None

    async def revoke_refresh_token(self, token: str) -> bool:
        """
        Revoke a refresh token (logout).
        Returns True if successful, False otherwise.
        """
        if not self._available:
            return False

        token_hash = hashlib.sha256(token.encode()).hexdigest()

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        UPDATE refresh_tokens
                        SET is_revoked = TRUE
                        WHERE token_hash = %s
                        """,
                        (token_hash,)
                    )
                    logger.info("[Auth] Revoked refresh token")
                    return True

        except Exception as e:
            logger.error(f"[Auth] Error revoking refresh token: {e}")
            return False

    async def cleanup_expired_tokens(self) -> int:
        """
        Clean up expired refresh tokens.
        Returns number of tokens deleted.
        """
        if not self._available:
            return 0

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        DELETE FROM refresh_tokens
                        WHERE expires_at < NOW() OR is_revoked = TRUE
                        """
                    )
                    deleted = cursor.rowcount
                    if deleted > 0:
                        logger.info(f"[Auth] Cleaned up {deleted} expired/revoked tokens")
                    return deleted

        except Exception as e:
            logger.error(f"[Auth] Error cleaning up tokens: {e}")
            return 0
