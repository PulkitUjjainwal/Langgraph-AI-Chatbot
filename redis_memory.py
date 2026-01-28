"""
Redis-based Memory Management for Chatbot
- Conversation history persistence
- Dynamic content embeddings cache
- Session management
"""

import json
import pickle
import hashlib
from typing import Optional, Dict, Any, List, Iterator, Sequence, Tuple
from datetime import datetime, timedelta
import numpy as np
import redis
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointTuple, CheckpointMetadata
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langchain_core.runnables.config import RunnableConfig


class RedisMemoryManager:
    """
    Redis-based memory manager for chatbot

    Storage Structure:
    - conv:{thread_id}:history → Conversation messages (JSON)
    - conv:{thread_id}:checkpoint → LangGraph checkpoint (pickle)
    - embed:{session_id}:{url_hash} → Dynamic embeddings (numpy array)
    - embed:{session_id}:chunks → Dynamic chunks (JSON)
    - session:{session_id}:meta → Session metadata
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        ttl_days: int = 7
    ):
        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=False  # Keep binary for embeddings
        )

        self.ttl_seconds = ttl_days * 24 * 3600

        # Test connection
        try:
            self.client.ping()
            print(f"[OK] Redis connected: {host}:{port}")
        except redis.ConnectionError as e:
            print(f"[ERROR] Redis connection failed: {e}")
            raise

    # ========================================================================
    # CONVERSATION HISTORY
    # ========================================================================

    def save_conversation(self, thread_id: str, messages: List[Dict[str, Any]]):
        """Save conversation history"""
        key = f"conv:{thread_id}:history"

        # Store as JSON
        data = {
            "thread_id": thread_id,
            "messages": messages,
            "last_updated": datetime.now().isoformat()
        }

        self.client.setex(
            key,
            self.ttl_seconds,
            json.dumps(data)
        )

    def get_conversation(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get conversation history"""
        key = f"conv:{thread_id}:history"
        data = self.client.get(key)

        if data:
            parsed = json.loads(data)
            return parsed.get("messages", [])

        return []

    def delete_conversation(self, thread_id: str):
        """Delete conversation history"""
        key = f"conv:{thread_id}:history"
        self.client.delete(key)

    # ========================================================================
    # DYNAMIC EMBEDDINGS CACHE
    # ========================================================================

    def _delete_url_embeddings(self, session_id: str, url_hash: str) -> int:
        """
        Delete all Redis keys associated with a URL's embeddings

        This is a private helper method used during FIFO cleanup.
        Deletes embeddings, chunks, metadata, and full content for the specified URL.

        Args:
            session_id: Session identifier
            url_hash: URL hash to delete

        Returns:
            Number of keys deleted
        """
        keys_to_delete = [
            f"embed:{session_id}:{url_hash}",
            f"embed:{session_id}:{url_hash}:chunks",
            f"embed:{session_id}:{url_hash}:meta",
            f"embed:{session_id}:{url_hash}:content"
        ]

        deleted_count = self.client.delete(*keys_to_delete)

        if deleted_count > 0:
            print(f"  [CLEANUP] Deleted {deleted_count} Redis keys for {session_id}/{url_hash}")
        else:
            print(f"  [WARNING] No keys found to delete for {session_id}/{url_hash}")

        return deleted_count

    def save_embeddings(
        self,
        session_id: str,
        dynamic_url: str,
        embeddings: np.ndarray,
        chunks: List[Dict[str, Any]],
        full_content: str = "",
        max_urls: int = 10
    ):
        """
        Save dynamic content embeddings to Redis with FIFO cache management

        When session reaches max_urls capacity and a new URL is added:
        1. Identifies oldest URL from tracking list
        2. Deletes all Redis keys for oldest URL (embeddings, chunks, metadata, content)
        3. Removes oldest URL from tracking list
        4. Adds new URL to tracking list
        5. Saves new embeddings and content to Redis

        Args:
            session_id: Session identifier
            dynamic_url: URL of dynamic content
            embeddings: NumPy array of embeddings
            chunks: List of text chunks
            full_content: Full original content text (for LLM context)
            max_urls: Maximum URLs to keep per session (default: 10)
        """
        url_hash = hashlib.md5(dynamic_url.encode()).hexdigest()[:16]

        # Get current URL tracking list
        list_key = f"session:{session_id}:urls"
        current_urls = [u.decode() for u in self.client.lrange(list_key, 0, -1)]

        # FIFO cleanup: If at capacity and adding NEW url, remove oldest
        url_to_remove = None
        if len(current_urls) >= max_urls and url_hash not in current_urls:
            url_to_remove = current_urls[0]  # Oldest URL (first in list)
            print(f"  [FIFO] Session at capacity ({max_urls} URLs), removing oldest: {url_to_remove}")

            # Delete all Redis keys for the old URL
            self._delete_url_embeddings(session_id, url_to_remove)

        # Save embeddings (binary)
        embed_key = f"embed:{session_id}:{url_hash}"
        self.client.setex(
            embed_key,
            self.ttl_seconds,
            pickle.dumps(embeddings)
        )

        # Save chunks (JSON)
        chunks_key = f"embed:{session_id}:{url_hash}:chunks"
        self.client.setex(
            chunks_key,
            self.ttl_seconds,
            json.dumps(chunks)
        )

        # Save metadata
        meta_key = f"embed:{session_id}:{url_hash}:meta"
        metadata = {
            "url": dynamic_url,
            "url_hash": url_hash,
            "embedding_shape": embeddings.shape,
            "chunk_count": len(chunks),
            "created_at": datetime.now().isoformat()
        }
        self.client.setex(
            meta_key,
            self.ttl_seconds,
            json.dumps(metadata)
        )

        # Save full content (for LLM context)
        if full_content:
            content_key = f"embed:{session_id}:{url_hash}:content"
            self.client.setex(
                content_key,
                self.ttl_seconds,
                full_content
            )

        # Track URL in session list (FIFO)
        if url_hash not in current_urls:
            self.client.rpush(list_key, url_hash)  # Add to right (newest)
            self.client.ltrim(list_key, -max_urls, -1)  # Keep only last N
            self.client.expire(list_key, self.ttl_seconds)

        # Calculate current count after potential cleanup
        final_count = min(len(current_urls) + 1 if url_hash not in current_urls else len(current_urls), max_urls)

        print(f"  [CACHE] Embeddings saved to Redis: {session_id}/{url_hash}")
        print(f"          Shape: {embeddings.shape}, Chunks: {len(chunks)}")
        print(f"  [SESSION] URLs tracked: {final_count}/{max_urls}")

    def get_embeddings(
        self,
        session_id: str,
        dynamic_url: str
    ) -> Optional[tuple[np.ndarray, List[Dict[str, Any]], str]]:
        """
        Get dynamic content embeddings from Redis

        Returns:
            (embeddings, chunks, full_content) or None if not found
        """
        url_hash = hashlib.md5(dynamic_url.encode()).hexdigest()[:16]

        embed_key = f"embed:{session_id}:{url_hash}"
        chunks_key = f"embed:{session_id}:{url_hash}:chunks"
        content_key = f"embed:{session_id}:{url_hash}:content"

        embed_data = self.client.get(embed_key)
        chunks_data = self.client.get(chunks_key)
        content_data = self.client.get(content_key)

        if embed_data and chunks_data:
            embeddings = pickle.loads(embed_data)
            chunks = json.loads(chunks_data)
            full_content = content_data.decode('utf-8') if content_data else ""

            print(f"  [CACHE HIT] Embeddings loaded from Redis: {session_id}/{url_hash}")
            if full_content:
                print(f"  [CACHE HIT] Content loaded: {len(full_content)} chars")
            return embeddings, chunks, full_content

        return None

    def get_session_urls(self, session_id: str) -> List[str]:
        """
        Get list of URL hashes tracked for this session

        Returns:
            List of URL hashes (in FIFO order, oldest first)
        """
        list_key = f"session:{session_id}:urls"
        urls = [u.decode() for u in self.client.lrange(list_key, 0, -1)]
        return urls

    def get_session_url_count(self, session_id: str) -> int:
        """
        Get count of URLs tracked for this session

        Returns:
            Number of URLs in session tracking list
        """
        list_key = f"session:{session_id}:urls"
        return self.client.llen(list_key)

    def delete_embeddings(self, session_id: str, dynamic_url: str):
        """
        Manually delete embeddings for a specific URL

        Note: This is for manual cleanup. FIFO cleanup happens automatically
        in save_embeddings() when session reaches max capacity.

        Args:
            session_id: Session identifier
            dynamic_url: Full URL to delete embeddings for
        """
        url_hash = hashlib.md5(dynamic_url.encode()).hexdigest()[:16]

        # Delete embeddings using private helper
        deleted_count = self._delete_url_embeddings(session_id, url_hash)

        # Remove from session URL tracking list
        list_key = f"session:{session_id}:urls"
        self.client.lrem(list_key, 0, url_hash)  # Remove all occurrences

        return deleted_count

    # ========================================================================
    # GLOBAL EMBEDDINGS CACHE (Shared across all users)
    # ========================================================================

    def save_embeddings_global(
        self,
        dynamic_url: str,
        embeddings: np.ndarray,
        chunks: List[Dict[str, Any]],
        full_content: str = "",
        ttl_days: int = 7
    ):
        """
        Save embeddings to GLOBAL cache (shared across all users)

        This is much more efficient for 10k+ users:
        - Same company URL cached once, used by all users
        - Reduces memory usage by 100-1000x
        - Reduces API calls and embedding generation by 100-1000x

        Args:
            dynamic_url: URL of dynamic content
            embeddings: NumPy array of embeddings
            chunks: List of text chunks
            full_content: Full original content text
            ttl_days: Time-to-live in days (default: 7)
        """
        url_hash = hashlib.md5(dynamic_url.encode()).hexdigest()[:16]
        ttl_seconds = ttl_days * 24 * 3600

        # Global keys (no session_id - shared across all users)
        embed_key = f"embed:global:{url_hash}"
        chunks_key = f"embed:global:{url_hash}:chunks"
        content_key = f"embed:global:{url_hash}:content"
        meta_key = f"embed:global:{url_hash}:meta"

        # Save embeddings (binary)
        self.client.setex(
            embed_key,
            ttl_seconds,
            pickle.dumps(embeddings)
        )

        # Save chunks (JSON)
        self.client.setex(
            chunks_key,
            ttl_seconds,
            json.dumps(chunks)
        )

        # Save full content (for LLM context)
        if full_content:
            self.client.setex(
                content_key,
                ttl_seconds,
                full_content
            )

        # Save metadata with access tracking
        metadata = {
            "url": dynamic_url,
            "url_hash": url_hash,
            "embedding_shape": embeddings.shape,
            "chunk_count": len(chunks),
            "created_at": datetime.now().isoformat(),
            "access_count": 0,
            "cache_type": "global"
        }
        self.client.setex(
            meta_key,
            ttl_seconds,
            json.dumps(metadata)
        )

        print(f"  [GLOBAL CACHE] Embeddings saved: {url_hash}")
        print(f"                 URL: {dynamic_url}")
        print(f"                 Shape: {embeddings.shape}, Chunks: {len(chunks)}")
        print(f"                 TTL: {ttl_days} days")

    def get_embeddings_global(
        self,
        dynamic_url: str
    ) -> Optional[tuple[np.ndarray, List[Dict[str, Any]], str]]:
        """
        Get embeddings from GLOBAL cache (shared across all users)

        Returns:
            (embeddings, chunks, full_content) or None if not found
        """
        url_hash = hashlib.md5(dynamic_url.encode()).hexdigest()[:16]

        embed_key = f"embed:global:{url_hash}"
        chunks_key = f"embed:global:{url_hash}:chunks"
        content_key = f"embed:global:{url_hash}:content"
        meta_key = f"embed:global:{url_hash}:meta"

        embed_data = self.client.get(embed_key)
        chunks_data = self.client.get(chunks_key)
        content_data = self.client.get(content_key)

        if embed_data and chunks_data:
            embeddings = pickle.loads(embed_data)
            chunks = json.loads(chunks_data)
            full_content = content_data.decode('utf-8') if content_data else ""

            # Increment access count
            meta_data = self.client.get(meta_key)
            if meta_data:
                metadata = json.loads(meta_data)
                metadata["access_count"] = metadata.get("access_count", 0) + 1
                metadata["last_accessed"] = datetime.now().isoformat()
                ttl = self.client.ttl(meta_key)
                if ttl > 0:
                    self.client.setex(meta_key, ttl, json.dumps(metadata))

            print(f"  [GLOBAL CACHE HIT] {url_hash}")
            if full_content:
                print(f"                     Content: {len(full_content)} chars")
            return embeddings, chunks, full_content

        return None

    def track_session_url(self, session_id: str, url_hash: str, max_urls: int = 10):
        """
        Track which URLs a session has accessed (lightweight)

        This is MUCH lighter than storing full embeddings per session:
        - Only stores URL hash reference (16 bytes)
        - Not the full embeddings (500KB+)

        Args:
            session_id: Session identifier
            url_hash: URL hash to track
            max_urls: Maximum URLs to track per session
        """
        list_key = f"session:{session_id}:global_urls"

        # Add to list (if not already present)
        current_urls = [u.decode() for u in self.client.lrange(list_key, 0, -1)]
        if url_hash not in current_urls:
            self.client.lpush(list_key, url_hash)
            self.client.ltrim(list_key, 0, max_urls - 1)  # Keep only last N

        # Set expiry
        self.client.expire(list_key, 24 * 3600)  # 24 hour TTL

    def get_session_global_urls(self, session_id: str) -> List[str]:
        """
        Get list of global URLs accessed by this session

        Returns:
            List of URL hashes
        """
        list_key = f"session:{session_id}:global_urls"
        urls = [u.decode() for u in self.client.lrange(list_key, 0, -1)]
        return urls

    def delete_embeddings_global(self, dynamic_url: str) -> int:
        """
        Delete embeddings from global cache

        Args:
            dynamic_url: Full URL to delete

        Returns:
            Number of keys deleted
        """
        url_hash = hashlib.md5(dynamic_url.encode()).hexdigest()[:16]

        keys_to_delete = [
            f"embed:global:{url_hash}",
            f"embed:global:{url_hash}:chunks",
            f"embed:global:{url_hash}:meta",
            f"embed:global:{url_hash}:content"
        ]

        deleted_count = self.client.delete(*keys_to_delete)

        if deleted_count > 0:
            print(f"  [GLOBAL CACHE] Deleted {deleted_count} keys for {url_hash}")

        return deleted_count

    # ========================================================================
    # MESSAGE PERSISTENCE (Chat History)
    # ========================================================================

    def save_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        """
        Save a single message to the session's message history.

        Messages are stored in a Redis list for ordered retrieval.
        Each message includes: role, content, timestamp, message_id

        Args:
            session_id: Session identifier
            message: Message dict with role, content, and optional metadata

        Returns:
            True if saved successfully
        """
        key = f"session:{session_id}:messages"

        # Ensure message has required fields
        msg_data = {
            "role": message.get("role", "unknown"),
            "content": message.get("content", ""),
            "timestamp": message.get("timestamp", datetime.now().isoformat()),
            "message_id": message.get("message_id", f"msg-{datetime.now().timestamp()}")
        }

        # Add any additional metadata
        for k, v in message.items():
            if k not in msg_data:
                msg_data[k] = v

        try:
            # Push to end of list (newest last)
            self.client.rpush(key, json.dumps(msg_data))
            # Trim to keep only last 100 messages per session
            self.client.ltrim(key, -100, -1)
            # Set/refresh TTL
            self.client.expire(key, self.ttl_seconds)
            return True
        except Exception as e:
            print(f"[MESSAGES] Error saving message: {e}")
            return False

    def get_messages(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieve message history for a session.

        Args:
            session_id: Session identifier
            limit: Maximum number of messages to return (default: 50)

        Returns:
            List of message dicts in chronological order
        """
        key = f"session:{session_id}:messages"

        try:
            # Get last N messages
            raw_messages = self.client.lrange(key, -limit, -1)

            messages = []
            for raw in raw_messages:
                try:
                    msg = json.loads(raw)
                    messages.append(msg)
                except json.JSONDecodeError:
                    continue

            return messages
        except Exception as e:
            print(f"[MESSAGES] Error getting messages: {e}")
            return []

    def clear_messages(self, session_id: str) -> bool:
        """
        Clear all messages for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared successfully
        """
        key = f"session:{session_id}:messages"

        try:
            self.client.delete(key)
            print(f"[MESSAGES] Cleared messages for session: {session_id}")
            return True
        except Exception as e:
            print(f"[MESSAGES] Error clearing messages: {e}")
            return False

    def get_message_count(self, session_id: str) -> int:
        """
        Get the number of messages in a session.

        Args:
            session_id: Session identifier

        Returns:
            Number of messages
        """
        key = f"session:{session_id}:messages"

        try:
            return self.client.llen(key)
        except Exception as e:
            print(f"[MESSAGES] Error getting message count: {e}")
            return 0

    def save_suggested_questions(self, session_id: str, questions: List[str]) -> bool:
        """
        Save suggested questions for a session (for persistence across refresh).

        Args:
            session_id: Session identifier
            questions: List of suggested question strings

        Returns:
            True if saved successfully
        """
        key = f"session:{session_id}:suggested_questions"

        try:
            self.client.setex(
                key,
                self.ttl_seconds,
                json.dumps(questions)
            )
            return True
        except Exception as e:
            print(f"[MESSAGES] Error saving suggested questions: {e}")
            return False

    def get_suggested_questions(self, session_id: str) -> List[str]:
        """
        Get suggested questions for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of suggested question strings
        """
        key = f"session:{session_id}:suggested_questions"

        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"[MESSAGES] Error getting suggested questions: {e}")

        return []

    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================

    def update_session_meta(self, session_id: str, data: Dict[str, Any]):
        """Update session metadata"""
        key = f"session:{session_id}:meta"

        # Get existing data
        existing = self.client.get(key)
        if existing:
            meta = json.loads(existing)
        else:
            meta = {}

        # Merge with new data
        meta.update(data)
        meta["last_activity"] = datetime.now().isoformat()

        self.client.setex(
            key,
            self.ttl_seconds,
            json.dumps(meta)
        )

    def get_session_meta(self, session_id: str) -> Dict[str, Any]:
        """Get session metadata"""
        key = f"session:{session_id}:meta"
        data = self.client.get(key)

        if data:
            return json.loads(data)

        return {}

    def cleanup_expired_sessions(self) -> int:
        """
        Cleanup expired sessions (handled automatically by Redis TTL)
        Returns count of active sessions
        """
        pattern = "session:*:meta"
        keys = self.client.keys(pattern)
        return len(keys)

    # ========================================================================
    # CACHE STATISTICS
    # ========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive cache statistics

        Returns:
            Dictionary containing:
            - conversations: Number of conversation histories
            - embeddings: Number of embedding caches
            - sessions: Number of active sessions
            - url_tracking_lists: Number of session URL tracking lists
            - memory_used_mb: Current memory usage in MB
            - memory_peak_mb: Peak memory usage in MB
        """
        conv_keys = len(self.client.keys("conv:*:history"))
        embed_keys = len(self.client.keys("embed:*"))
        session_keys = len(self.client.keys("session:*:meta"))
        url_lists = len(self.client.keys("session:*:urls"))

        # Memory usage
        info = self.client.info("memory")

        return {
            "conversations": conv_keys,
            "embeddings": embed_keys,
            "sessions": session_keys,
            "url_tracking_lists": url_lists,
            "memory_used_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
            "memory_peak_mb": round(info.get("used_memory_peak", 0) / 1024 / 1024, 2)
        }

    def get_session_detailed_stats(self, session_id: str) -> Dict[str, Any]:
        """
        Get detailed statistics for a specific session

        Args:
            session_id: Session identifier

        Returns:
            Dictionary containing session-specific stats
        """
        urls = self.get_session_urls(session_id)
        url_count = len(urls)

        # Count embedding keys for this session
        embed_pattern = f"embed:{session_id}:*"
        embed_keys = self.client.keys(embed_pattern)

        return {
            "session_id": session_id,
            "tracked_urls": url_count,
            "url_hashes": urls,
            "embedding_keys_count": len(embed_keys),
            "metadata": self.get_session_meta(session_id)
        }

    def clear_all(self):
        """Clear all data (use with caution!)"""
        self.client.flushdb()
        print("[WARNING] Redis database cleared")


class RedisCheckpointSaver(BaseCheckpointSaver):
    """
    LangGraph checkpoint saver using Redis
    Stores conversation state for LangGraph workflows
    """

    def __init__(self, redis_manager: RedisMemoryManager):
        super().__init__()
        self.redis = redis_manager
        self.serde = JsonPlusSerializer()

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | int | float]
    ) -> RunnableConfig:
        """Save checkpoint to Redis"""
        thread_id = config.get("configurable", {}).get("thread_id")

        if not thread_id:
            return config

        # Serialize checkpoint using serde
        checkpoint_data = {
            "checkpoint": self.serde.dumps_typed(checkpoint),
            "metadata": metadata,
            "timestamp": datetime.now().isoformat()
        }

        key = f"conv:{thread_id}:checkpoint"
        self.redis.client.setex(
            key,
            self.redis.ttl_seconds,
            pickle.dumps(checkpoint_data)
        )

        return config

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str
    ) -> None:
        """Store intermediate writes linked to a checkpoint"""
        thread_id = config.get("configurable", {}).get("thread_id")

        if not thread_id:
            return

        # Store writes for this checkpoint
        key = f"conv:{thread_id}:writes:{task_id}"
        writes_data = {
            "writes": writes,
            "task_id": task_id,
            "timestamp": datetime.now().isoformat()
        }

        self.redis.client.setex(
            key,
            self.redis.ttl_seconds,
            pickle.dumps(writes_data)
        )

    def get(self, config: RunnableConfig) -> Optional[Checkpoint]:
        """Get checkpoint from Redis"""
        thread_id = config.get("configurable", {}).get("thread_id")

        if not thread_id:
            return None

        key = f"conv:{thread_id}:checkpoint"
        data = self.redis.client.get(key)

        if data:
            checkpoint_data = pickle.loads(data)
            return self.serde.loads_typed(checkpoint_data["checkpoint"])

        return None

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Get checkpoint tuple from Redis"""
        thread_id = config.get("configurable", {}).get("thread_id")

        if not thread_id:
            return None

        key = f"conv:{thread_id}:checkpoint"
        data = self.redis.client.get(key)

        if data:
            checkpoint_data = pickle.loads(data)
            checkpoint = self.serde.loads_typed(checkpoint_data["checkpoint"])
            metadata = checkpoint_data.get("metadata", {})

            # Return CheckpointTuple object as expected by LangGraph
            return CheckpointTuple(
                config=config,
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=None,
                pending_writes=None
            )

        return None

    def list(
        self,
        config: Optional[RunnableConfig] = None,
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints (simplified implementation)"""
        # For simplicity, return empty iterator
        # Full implementation would store checkpoint history and filter results
        return iter([])

    def get_next_version(self, current: Optional[Any], channel: Any) -> Any:
        """Generate the next version ID for a channel"""
        # Simple version increment
        if current is None:
            return 1
        return current + 1
