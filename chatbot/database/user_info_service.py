"""
User Info Service Module

Stores user information collected through natural conversation flow.
Progressive collection: name, email, phone, requirements.

Features:
- Async MySQL storage with connection pooling
- Fallback to JSON file logging if MySQL unavailable
- CRUD operations for user info
- Analytics and statistics queries
- Background task compatible (non-blocking)
"""

import asyncio
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import asdict

# MySQL connector - using aiomysql for async support
try:
    import aiomysql
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    print("[UserInfoService] Warning: aiomysql not installed. Run: pip install aiomysql")


class UserInfoService:
    """
    Service for storing and retrieving user information.

    Features:
    - Async MySQL storage with connection pooling
    - Fallback to JSON file logging if MySQL unavailable
    - CRUD operations for user info
    - Analytics queries for conversion metrics
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "chatbot",
        pool_size: int = 5,
        fallback_log_path: str = "logs/user_info_fallback.json"
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        self.fallback_log_path = fallback_log_path

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
            print("[UserInfoService] MySQL not available - using file fallback")
            self._setup_fallback_logging()
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
                autocommit=True,
                connect_timeout=5
            )

            # Test connection
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    await cur.fetchone()

            self._available = True
            print(f"[UserInfoService] MySQL connection pool initialized")
            return True

        except Exception as e:
            print(f"[UserInfoService] MySQL connection failed: {e}")
            print("[UserInfoService] Using file fallback for user info storage")
            self._setup_fallback_logging()
            return False

    def _setup_fallback_logging(self):
        """Setup fallback JSON file logging"""
        log_dir = os.path.dirname(self.fallback_log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    async def save_user_info(
        self,
        session_id: str,
        field: str,
        value: str,
        state_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Save or update user information field.

        Args:
            session_id: Session identifier
            field: Field name (name, email, phone, requirements)
            value: Field value
            state_data: Complete state data for update

        Returns:
            Dict with 'success' bool and info
        """
        # Ensure initialized
        if not self._initialized:
            await self.initialize()

        if self._available:
            return await self._save_to_mysql(session_id, field, value, state_data)
        else:
            return self._save_to_file(session_id, field, value, state_data)

    async def _save_to_mysql(
        self,
        session_id: str,
        field: str,
        value: str,
        state_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Save user info to MySQL database"""
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # Check if record exists
                    await cur.execute("""
                        SELECT id FROM user_info WHERE session_id = %s
                    """, (session_id,))

                    existing = await cur.fetchone()

                    if existing:
                        # Update existing record
                        update_fields = [f"{field} = %s"]
                        params = [value]

                        if state_data:
                            # Update additional fields from state
                            for key in ['completion_percentage', 'fields_collected',
                                       'name_ask_count', 'email_ask_count', 'phone_ask_count',
                                       'requirements_ask_count', 'collection_paused',
                                       'last_field_asked', 'pause_until_message_count']:
                                if key in state_data:
                                    db_value = state_data[key]
                                    # Convert list to JSON string
                                    if key == 'fields_collected' and isinstance(db_value, list):
                                        db_value = json.dumps(db_value)
                                    update_fields.append(f"{key} = %s")
                                    params.append(db_value)

                            # Update first_field_at if this is the first field
                            if state_data.get('first_field_at') and not existing:
                                update_fields.append("first_field_at = %s")
                                params.append(datetime.now())

                            # Update completed_at if completion reaches 100%
                            if state_data.get('completion_percentage', 0) >= 1.0:
                                update_fields.append("completed_at = %s")
                                params.append(datetime.now())

                        update_fields.append("updated_at = CURRENT_TIMESTAMP")
                        params.append(session_id)

                        query = f"""
                            UPDATE user_info
                            SET {', '.join(update_fields)}
                            WHERE session_id = %s
                        """
                        await cur.execute(query, params)

                    else:
                        # Insert new record
                        fields_collected = state_data.get('fields_collected', [field]) if state_data else [field]
                        completion = state_data.get('completion_percentage', 0.3) if state_data else 0.3

                        # Convert requirements dict to JSON if it's the requirements field
                        db_value = value
                        if field == 'requirements' and isinstance(value, dict):
                            db_value = json.dumps(value)

                        await cur.execute("""
                            INSERT INTO user_info (
                                session_id, {field}, completion_percentage, fields_collected,
                                first_field_at, last_field_asked, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """.format(field=field), (
                            session_id,
                            db_value,
                            completion,
                            json.dumps(fields_collected),
                            datetime.now(),
                            field
                        ))

                        # Update conversation_sessions table
                        await cur.execute("""
                            UPDATE conversation_sessions
                            SET user_info_collected = TRUE,
                                user_name = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE session_id = %s
                        """, (value if field == 'name' else None, session_id))

                    print(f"[UserInfoService] Saved {field} for session {session_id}")
                    return {
                        "success": True,
                        "session_id": session_id,
                        "field": field,
                        "storage": "mysql"
                    }

        except Exception as e:
            print(f"[UserInfoService] MySQL storage error: {e}")
            # Fallback to file
            return self._save_to_file(session_id, field, value, state_data)

    def _save_to_file(
        self,
        session_id: str,
        field: str,
        value: str,
        state_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Fallback: Store user info to JSON file"""
        try:
            data = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "field": field,
                "value": value,
                "state_data": state_data
            }

            # Append to JSON file (one JSON object per line)
            with open(self.fallback_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")

            print(f"[UserInfoService] Saved {field} for session {session_id} to file")
            return {
                "success": True,
                "session_id": session_id,
                "field": field,
                "storage": "file"
            }

        except Exception as e:
            print(f"[UserInfoService] File storage error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def update_user_info(
        self,
        session_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update specific fields in user_info table.
        Used for updating rejection counts and other metadata.

        Args:
            session_id: Session identifier
            updates: Dict of field_name -> value to update

        Returns:
            Dict with 'success' bool and info
        """
        if not self._initialized:
            await self.initialize()

        if not self._available:
            return {"success": False, "error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # Build UPDATE query
                    update_fields = []
                    params = []

                    for field_name, value in updates.items():
                        # Convert lists to JSON strings
                        if isinstance(value, list):
                            value = json.dumps(value)

                        update_fields.append(f"{field_name} = %s")
                        params.append(value)

                    if not update_fields:
                        return {"success": False, "error": "No fields to update"}

                    # Add updated_at timestamp
                    update_fields.append("updated_at = CURRENT_TIMESTAMP")
                    params.append(session_id)

                    query = f"""
                        UPDATE user_info
                        SET {', '.join(update_fields)}
                        WHERE session_id = %s
                    """
                    await cur.execute(query, params)

                    print(f"[UserInfoService] Updated user_info for session {session_id}: {list(updates.keys())}")
                    return {
                        "success": True,
                        "session_id": session_id,
                        "updated_fields": list(updates.keys())
                    }

        except Exception as e:
            print(f"[UserInfoService] Update error: {e}")
            return {"success": False, "error": str(e)}

    async def get_user_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user info for a session.

        Args:
            session_id: Session identifier

        Returns:
            Dict with user info or None if not found
        """
        if not self._available:
            return None

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT * FROM user_info
                        WHERE session_id = %s
                    """, (session_id,))

                    user_info = await cur.fetchone()

                    if not user_info:
                        return None

                    # Parse JSON fields
                    if user_info.get('fields_collected'):
                        try:
                            user_info['fields_collected'] = json.loads(user_info['fields_collected'])
                        except:
                            user_info['fields_collected'] = []

                    if user_info.get('requirements'):
                        try:
                            user_info['requirements'] = json.loads(user_info['requirements'])
                        except:
                            user_info['requirements'] = None

                    # Convert timestamps to ISO format
                    for field in ['first_field_at', 'completed_at', 'last_ask_at', 'created_at', 'updated_at']:
                        if user_info.get(field):
                            user_info[field] = user_info[field].isoformat()

                    return user_info

        except Exception as e:
            print(f"[UserInfoService] Get user info error: {e}")
            return None

    async def update_collection_pause(
        self,
        session_id: str,
        paused: bool,
        pause_until_message_count: Optional[int] = None
    ) -> bool:
        """
        Update collection pause state.

        Args:
            session_id: Session identifier
            paused: Whether to pause collection
            pause_until_message_count: Resume after this message count

        Returns:
            True if successful
        """
        if not self._available:
            return False

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        UPDATE user_info
                        SET collection_paused = %s,
                            pause_until_message_count = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE session_id = %s
                    """, (paused, pause_until_message_count, session_id))

            return True

        except Exception as e:
            print(f"[UserInfoService] Update pause error: {e}")
            return False

    async def get_user_info_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get user info collection statistics for the last N days"""
        if not self._available:
            return {"error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT
                            COUNT(*) as total_sessions_with_info,
                            SUM(CASE WHEN name IS NOT NULL THEN 1 ELSE 0 END) as sessions_with_name,
                            SUM(CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) as sessions_with_email,
                            SUM(CASE WHEN phone IS NOT NULL THEN 1 ELSE 0 END) as sessions_with_phone,
                            SUM(CASE WHEN requirements IS NOT NULL THEN 1 ELSE 0 END) as sessions_with_requirements,
                            AVG(completion_percentage) * 100 as avg_completion_percentage,
                            SUM(CASE WHEN completion_percentage >= 0.6 THEN 1 ELSE 0 END) as sessions_60_plus_complete,
                            SUM(CASE WHEN collection_paused = TRUE THEN 1 ELSE 0 END) as sessions_with_resistance,
                            AVG(name_ask_count) as avg_name_asks,
                            AVG(email_ask_count) as avg_email_asks,
                            AVG(phone_ask_count) as avg_phone_asks
                        FROM user_info
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    """, (days,))

                    stats = await cur.fetchone()

                    return {
                        "period_days": days,
                        "total_sessions_with_info": stats['total_sessions_with_info'] or 0,
                        "sessions_with_name": stats['sessions_with_name'] or 0,
                        "sessions_with_email": stats['sessions_with_email'] or 0,
                        "sessions_with_phone": stats['sessions_with_phone'] or 0,
                        "sessions_with_requirements": stats['sessions_with_requirements'] or 0,
                        "avg_completion_percentage": round(stats['avg_completion_percentage'], 2) if stats['avg_completion_percentage'] else 0,
                        "sessions_60_plus_complete": stats['sessions_60_plus_complete'] or 0,
                        "sessions_with_resistance": stats['sessions_with_resistance'] or 0,
                        "avg_name_asks": round(stats['avg_name_asks'], 2) if stats['avg_name_asks'] else 0,
                        "avg_email_asks": round(stats['avg_email_asks'], 2) if stats['avg_email_asks'] else 0,
                        "avg_phone_asks": round(stats['avg_phone_asks'], 2) if stats['avg_phone_asks'] else 0
                    }

        except Exception as e:
            print(f"[UserInfoService] Stats error: {e}")
            return {"error": str(e)}

    async def get_daily_collection_metrics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get daily collection metrics.

        Args:
            days: Number of days to include

        Returns:
            Dict with daily breakdown
        """
        if not self._available:
            return {"error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT
                            DATE(ui.created_at) as date,
                            COUNT(*) as sessions_with_collection,
                            SUM(CASE WHEN ui.name IS NOT NULL THEN 1 ELSE 0 END) as name_collected,
                            SUM(CASE WHEN ui.email IS NOT NULL THEN 1 ELSE 0 END) as email_collected,
                            SUM(CASE WHEN ui.phone IS NOT NULL THEN 1 ELSE 0 END) as phone_collected,
                            AVG(ui.completion_percentage) * 100 as avg_completion,
                            SUM(CASE WHEN ui.collection_paused = TRUE THEN 1 ELSE 0 END) as resistance_count
                        FROM user_info ui
                        WHERE ui.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        GROUP BY DATE(ui.created_at)
                        ORDER BY date DESC
                    """, (days,))

                    rows = await cur.fetchall()

                    # Convert dates to ISO format
                    for row in rows:
                        if row.get('date'):
                            row['date'] = row['date'].isoformat()
                        if row.get('avg_completion'):
                            row['avg_completion'] = round(row['avg_completion'], 2)

                    return {
                        "period_days": days,
                        "data": rows
                    }

        except Exception as e:
            print(f"[UserInfoService] Daily metrics error: {e}")
            return {"error": str(e)}

    async def get_collection_funnel(self, days: int = 30) -> Dict[str, Any]:
        """
        Get collection funnel analysis.

        Args:
            days: Number of days to include

        Returns:
            Dict with funnel stages
        """
        if not self._available:
            return {"error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Get total sessions
                    await cur.execute("""
                        SELECT COUNT(*) as total
                        FROM conversation_sessions
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    """, (days,))
                    total_sessions = (await cur.fetchone())['total']

                    # Get collection attempts
                    await cur.execute("""
                        SELECT COUNT(*) as total
                        FROM user_info
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    """, (days,))
                    collection_attempted = (await cur.fetchone())['total']

                    # Get name collected
                    await cur.execute("""
                        SELECT COUNT(*) as total
                        FROM user_info
                        WHERE name IS NOT NULL
                        AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    """, (days,))
                    name_collected = (await cur.fetchone())['total']

                    # Get email collected
                    await cur.execute("""
                        SELECT COUNT(*) as total
                        FROM user_info
                        WHERE email IS NOT NULL
                        AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    """, (days,))
                    email_collected = (await cur.fetchone())['total']

                    # Get phone collected
                    await cur.execute("""
                        SELECT COUNT(*) as total
                        FROM user_info
                        WHERE phone IS NOT NULL
                        AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    """, (days,))
                    phone_collected = (await cur.fetchone())['total']

                    funnel = [
                        {
                            "stage": "Total Sessions",
                            "count": total_sessions,
                            "percentage": 100.0
                        },
                        {
                            "stage": "Collection Attempted",
                            "count": collection_attempted,
                            "percentage": round((collection_attempted / total_sessions * 100) if total_sessions > 0 else 0, 2)
                        },
                        {
                            "stage": "Name Collected",
                            "count": name_collected,
                            "percentage": round((name_collected / total_sessions * 100) if total_sessions > 0 else 0, 2)
                        },
                        {
                            "stage": "Email Collected",
                            "count": email_collected,
                            "percentage": round((email_collected / total_sessions * 100) if total_sessions > 0 else 0, 2)
                        },
                        {
                            "stage": "Phone Collected",
                            "count": phone_collected,
                            "percentage": round((phone_collected / total_sessions * 100) if total_sessions > 0 else 0, 2)
                        }
                    ]

                    return {
                        "funnel": funnel,
                        "period_days": days
                    }

        except Exception as e:
            print(f"[UserInfoService] Funnel error: {e}")
            return {"error": str(e)}

    async def get_user_info_list(
        self,
        limit: int = 20,
        offset: int = 0,
        has_email: Optional[bool] = None,
        min_completion: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Get paginated list of user info.

        Args:
            limit: Number of records per page
            offset: Pagination offset
            has_email: Filter by email presence
            min_completion: Minimum completion percentage

        Returns:
            Dict with user info list and pagination info
        """
        if not self._available:
            return {"error": "MySQL not available", "user_infos": [], "total": 0}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Build WHERE clause
                    where_conditions = []
                    params = []

                    if has_email is not None:
                        if has_email:
                            where_conditions.append("email IS NOT NULL")
                        else:
                            where_conditions.append("email IS NULL")

                    if min_completion is not None:
                        where_conditions.append("completion_percentage >= %s")
                        params.append(min_completion)

                    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

                    # Get total count
                    await cur.execute(f"""
                        SELECT COUNT(*) as total
                        FROM user_info
                        WHERE {where_clause}
                    """, params)

                    total = (await cur.fetchone())['total']

                    # Get paginated results
                    await cur.execute(f"""
                        SELECT
                            id, session_id, name, email, phone,
                            completion_percentage, fields_collected, collection_paused,
                            created_at, updated_at
                        FROM user_info
                        WHERE {where_clause}
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                    """, params + [limit, offset])

                    user_infos = await cur.fetchall()

                    # Parse JSON and convert timestamps
                    for info in user_infos:
                        if info.get('fields_collected'):
                            try:
                                info['fields_collected'] = json.loads(info['fields_collected'])
                            except:
                                info['fields_collected'] = []

                        for field in ['created_at', 'updated_at']:
                            if info.get(field):
                                info[field] = info[field].isoformat()

                    return {
                        "user_infos": user_infos,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "has_more": (offset + limit) < total
                    }

        except Exception as e:
            print(f"[UserInfoService] Get user info list error: {e}")
            return {"error": str(e), "user_infos": [], "total": 0}

    async def close(self):
        """Close database connections"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            print("[UserInfoService] Connection pool closed")

    @property
    def is_available(self) -> bool:
        """Check if user info service is available"""
        return self._available


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_user_info_service: Optional[UserInfoService] = None


async def get_user_info_service() -> UserInfoService:
    """Get or create user info service singleton"""
    global _user_info_service

    if _user_info_service is None:
        from chatbot.config.settings import get_settings
        settings = get_settings()

        _user_info_service = UserInfoService(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            pool_size=settings.mysql_pool_size
        )

    return _user_info_service


async def init_user_info_service() -> Optional[UserInfoService]:
    """Initialize user info service and return it if successful"""
    service = await get_user_info_service()
    await service.initialize()
    return service
