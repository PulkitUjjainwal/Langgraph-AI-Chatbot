# Migration Plan: PostgreSQL + Redis Architecture

## Executive Summary

**Recommendation: HYBRID Vector Storage**
- **FAISS** for static knowledge base (keep existing)
- **pgvector** for dynamic/user content (new)
- **PostgreSQL** to replace MySQL
- **Redis** for hot cache (keep existing)

## Why Hybrid Approach?

| Scenario | Current Setup | Issue | Solution |
|----------|---------------|-------|----------|
| Static KB (2,300 chunks) | FAISS ✅ | None - working great | **Keep FAISS** |
| Dynamic embeddings | Redis | Not queryable, no persistence | **Add pgvector** |
| FAQ system | MySQL | Extra database | **Migrate to PostgreSQL** |
| Sessions/checkpoints | Redis ✅ | None - working great | **Keep Redis** |

### Performance Comparison

```
┌────────────────────────────────────────────────────────────────┐
│                    VECTOR SEARCH PERFORMANCE                    │
├────────────────────┬─────────────┬────────────┬────────────────┤
│ Operation          │ FAISS       │ pgvector   │ Recommendation │
├────────────────────┼─────────────┼────────────┼────────────────┤
│ Static KB search   │ <100ms ⚡   │ 200-500ms  │ FAISS          │
│ Dynamic search     │ N/A         │ 200-500ms  │ pgvector       │
│ Metadata filtering │ Complex     │ Easy (SQL) │ pgvector       │
│ Updates            │ Rebuild     │ INSERT     │ pgvector       │
│ Persistence        │ File        │ Database   │ pgvector       │
│ Memory usage       │ ~2MB        │ ~50MB      │ FAISS          │
│ Setup complexity   │ Easy        │ Moderate   │ FAISS          │
└────────────────────┴─────────────┴────────────┴────────────────┘
```

## Architecture After Migration

```
┌─────────────────────────────────────────────────────────────────┐
│                        FASTAPI APPLICATION                       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              LangGraph Workflow Engine                    │  │
│  │  (Redis checkpoint storage - NO CHANGE)                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────┐  ┌────────────────────────────────────┐ │
│  │ Static KB        │  │ Dynamic Content Retrieval          │ │
│  │ (FAISS) ⚡       │  │ (pgvector)                         │ │
│  │                  │  │                                    │ │
│  │ - 2,300 chunks   │  │ - User-generated content          │ │
│  │ - <100ms query   │  │ - API-fetched data                │ │
│  │ - In-memory      │  │ - Conversational history          │ │
│  │ - Immutable      │  │ - Metadata filtering              │ │
│  └──────────────────┘  └────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ▼
            ┌─────────────────────────────────────┐
            │         STORAGE LAYER               │
            │                                     │
            │  ┌─────────────┐  ┌──────────────┐ │
            │  │   Redis     │  │ PostgreSQL   │ │
            │  │  (Hot)      │  │  (Cold)      │ │
            │  ├─────────────┤  ├──────────────┤ │
            │  │ - Sessions  │  │ - Users      │ │
            │  │ - Cache     │  │ - FAQ        │ │
            │  │ - Checkpoint│  │ - Feedback   │ │
            │  │ - Temp      │  │ - Analytics  │ │
            │  │   embeddings│  │ - Messages   │ │
            │  │             │  │ - Embeddings │ │
            │  │ TTL: 7 days │  │   (pgvector) │ │
            │  │ Size: ~2GB  │  │ Size: ~20GB  │ │
            │  └─────────────┘  └──────────────┘ │
            └─────────────────────────────────────┘
```

## Migration Phases

### Phase 1: PostgreSQL Setup (Week 1)
**Status**: 🔵 Setup infrastructure

#### 1.1 Install PostgreSQL
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql postgresql-contrib

# Windows (download from postgresql.org)
# Or use Docker:
docker run -d \
  --name chatbot-postgres \
  -e POSTGRES_PASSWORD=yourpassword \
  -e POSTGRES_DB=chatbot \
  -p 5432:5432 \
  -v pgdata:/var/lib/postgresql/data \
  postgres:16-alpine
```

#### 1.2 Install pgvector Extension
```bash
# Connect to PostgreSQL
psql -U postgres

# Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

# Verify installation
SELECT * FROM pg_extension WHERE extname = 'vector';
```

#### 1.3 Python Dependencies
```python
# Add to requirements.txt
psycopg2-binary==2.9.9        # PostgreSQL driver
asyncpg==0.29.0                # Async PostgreSQL
pgvector==0.2.4                # pgvector support
sqlalchemy==2.0.25             # ORM (optional)
alembic==1.13.1                # Migrations (optional)
```

---

### Phase 2: Schema Migration (Week 1)
**Status**: 🟡 Migrate MySQL to PostgreSQL

#### 2.1 Create PostgreSQL Schema

**File**: `chatbot/database/postgres_schema.sql`

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- USERS & AUTHENTICATION
-- ============================================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user' CHECK (role IN ('super_admin', 'admin', 'user')),
    is_active BOOLEAN DEFAULT TRUE,
    must_change_password BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- Refresh tokens
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token ON refresh_tokens(token);

-- ============================================================================
-- FAQ SYSTEM
-- ============================================================================

CREATE TABLE pages (
    id SERIAL PRIMARY KEY,
    page_key VARCHAR(100) UNIQUE NOT NULL,
    page_name VARCHAR(255) NOT NULL,
    url_pattern VARCHAR(500) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE faq (
    id SERIAL PRIMARY KEY,
    page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    question_type VARCHAR(50) DEFAULT 'suggested' CHECK (question_type IN ('suggested', 'faq')),
    priority INTEGER DEFAULT 0,
    keywords TEXT,
    click_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_faq_page ON faq(page_id);
CREATE INDEX idx_faq_type ON faq(question_type);
CREATE INDEX idx_faq_priority ON faq(priority DESC);

-- Full-text search
CREATE INDEX idx_faq_question_fts ON faq USING gin(to_tsvector('english', question));
CREATE INDEX idx_faq_keywords_fts ON faq USING gin(to_tsvector('english', keywords));

-- ============================================================================
-- CONVERSATIONS & MESSAGES
-- ============================================================================

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(255) UNIQUE NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    site_id VARCHAR(50) NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT TRUE
) PARTITION BY RANGE (started_at);

-- Partition by month (create as needed)
CREATE TABLE conversations_2026_03 PARTITION OF conversations
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE INDEX idx_conversations_session ON conversations(session_id);
CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_conversations_activity ON conversations(last_activity);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) PARTITION BY RANGE (created_at);

-- Partition by month
CREATE TABLE messages_2026_03 PARTITION OF messages
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(created_at);

-- ============================================================================
-- VECTOR EMBEDDINGS (pgvector)
-- ============================================================================

CREATE TABLE embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_type VARCHAR(50) NOT NULL, -- 'dynamic_url', 'user_message', 'faq'
    content_id VARCHAR(255),            -- Reference to original content
    content_text TEXT NOT NULL,
    embedding vector(768),              -- Adjust dimension for your model
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP                -- For TTL cleanup
);

CREATE INDEX idx_embeddings_type ON embeddings(content_type);
CREATE INDEX idx_embeddings_content_id ON embeddings(content_id);
CREATE INDEX idx_embeddings_expires ON embeddings(expires_at) WHERE expires_at IS NOT NULL;

-- Vector similarity index (HNSW for fast ANN search)
CREATE INDEX idx_embeddings_vector_hnsw ON embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Alternative: IVFFlat index (better for smaller datasets)
-- CREATE INDEX idx_embeddings_vector_ivf ON embeddings
--     USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);

-- ============================================================================
-- FEEDBACK
-- ============================================================================

CREATE TABLE feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(255),
    message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    feedback_type VARCHAR(50) NOT NULL CHECK (feedback_type IN ('thumbs_up', 'thumbs_down', 'comment')),
    comment TEXT,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_feedback_session ON feedback(session_id);
CREATE INDEX idx_feedback_type ON feedback(feedback_type);
CREATE INDEX idx_feedback_created ON feedback(created_at);

-- ============================================================================
-- ANALYTICS (Materialized Views)
-- ============================================================================

CREATE MATERIALIZED VIEW mv_daily_stats AS
SELECT
    DATE(started_at) as date,
    site_id,
    COUNT(DISTINCT id) as total_conversations,
    COUNT(DISTINCT user_id) as unique_users,
    AVG(EXTRACT(EPOCH FROM (last_activity - started_at))) as avg_duration_seconds
FROM conversations
GROUP BY DATE(started_at), site_id;

CREATE UNIQUE INDEX idx_mv_daily_stats ON mv_daily_stats(date, site_id);

CREATE MATERIALIZED VIEW mv_faq_performance AS
SELECT
    f.id,
    f.question,
    f.page_id,
    f.click_count,
    COUNT(fb.id) as feedback_count,
    AVG(CASE WHEN fb.feedback_type = 'thumbs_up' THEN 1 ELSE 0 END) as positive_rate
FROM faq f
LEFT JOIN feedback fb ON fb.metadata->>'faq_id' = f.id::text
GROUP BY f.id, f.question, f.page_id, f.click_count;

CREATE UNIQUE INDEX idx_mv_faq_performance ON mv_faq_performance(id);

-- ============================================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_pages_updated_at BEFORE UPDATE ON pages
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_faq_updated_at BEFORE UPDATE ON faq
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Clean up expired embeddings
CREATE OR REPLACE FUNCTION cleanup_expired_embeddings()
RETURNS void AS $$
BEGIN
    DELETE FROM embeddings WHERE expires_at < CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- SEED DATA
-- ============================================================================

-- Default super admin user
INSERT INTO users (email, username, password_hash, full_name, role, must_change_password)
VALUES (
    'admin@exportgenius.in',
    'admin',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5Y5myHPP9I2ZS', -- Admin@123
    'System Administrator',
    'super_admin',
    TRUE
);

-- Insert pages (copy from your existing MySQL data)
INSERT INTO pages (page_key, page_name, url_pattern) VALUES
('home', 'Home Page', '/'),
('search_data', 'Search Data', '/search-data'),
('data_license', 'Data License', '/data-license'),
('logistics', 'Logistics', '/logistics'),
('platform', 'Platform', '/platform'),
('api', 'API', '/api');

-- Insert FAQ entries (migrate from your existing MySQL data)
-- You can use pg_dump from MySQL or manual INSERT statements

-- ============================================================================
-- MAINTENANCE TASKS
-- ============================================================================

-- Schedule materialized view refresh (use pg_cron or external scheduler)
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_stats;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_faq_performance;

-- Schedule embedding cleanup
-- SELECT cleanup_expired_embeddings();
```

#### 2.2 Migrate Existing Data

**Script**: `scripts/migrate_mysql_to_postgres.py`

```python
#!/usr/bin/env python3
"""
Migrate data from MySQL to PostgreSQL
"""
import asyncio
import os
from datetime import datetime
import mysql.connector
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def migrate():
    # Connect to MySQL
    mysql_conn = mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD'),
        database=os.getenv('MYSQL_DATABASE', 'chatbot')
    )
    mysql_cursor = mysql_conn.cursor(dictionary=True)

    # Connect to PostgreSQL
    pg_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database=os.getenv('POSTGRES_DATABASE', 'chatbot')
    )

    print("📦 Starting migration...")

    # 1. Migrate pages
    print("  ↳ Migrating pages...")
    mysql_cursor.execute("SELECT * FROM pages")
    pages = mysql_cursor.fetchall()
    for page in pages:
        await pg_conn.execute("""
            INSERT INTO pages (id, page_key, page_name, url_pattern, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (page_key) DO NOTHING
        """, page['id'], page['page_key'], page['page_name'], page['url_pattern'],
             page['is_active'], page.get('created_at'), page.get('updated_at'))
    print(f"    ✅ Migrated {len(pages)} pages")

    # 2. Migrate FAQ
    print("  ↳ Migrating FAQ...")
    mysql_cursor.execute("SELECT * FROM faq")
    faqs = mysql_cursor.fetchall()
    for faq in faqs:
        await pg_conn.execute("""
            INSERT INTO faq (id, page_id, question, answer, question_type, priority,
                             keywords, click_count, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT DO NOTHING
        """, faq['id'], faq['page_id'], faq['question'], faq['answer'],
             faq.get('question_type', 'suggested'), faq.get('priority', 0),
             faq.get('keywords'), faq.get('click_count', 0), faq.get('is_active', True),
             faq.get('created_at'), faq.get('updated_at'))
    print(f"    ✅ Migrated {len(faqs)} FAQ entries")

    # 3. Migrate users (if you have existing users in MySQL)
    print("  ↳ Migrating users...")
    try:
        mysql_cursor.execute("SELECT * FROM users")
        users = mysql_cursor.fetchall()
        for user in users:
            await pg_conn.execute("""
                INSERT INTO users (email, username, password_hash, full_name, role,
                                   is_active, must_change_password, created_at, updated_at, last_login)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (email) DO NOTHING
            """, user['email'], user['username'], user['password_hash'], user.get('full_name'),
                 user.get('role', 'user'), user.get('is_active', True),
                 user.get('must_change_password', False), user.get('created_at'),
                 user.get('updated_at'), user.get('last_login'))
        print(f"    ✅ Migrated {len(users)} users")
    except mysql.connector.errors.ProgrammingError:
        print("    ⚠️  No users table in MySQL, skipping")

    # Close connections
    mysql_cursor.close()
    mysql_conn.close()
    await pg_conn.close()

    print("✅ Migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate())
```

---

### Phase 3: Code Updates (Week 2)
**Status**: 🔵 Refactor application code

#### 3.1 PostgreSQL Database Client

**File**: `chatbot/integrations/postgres/client.py`

```python
"""
PostgreSQL database client with connection pooling
"""
import asyncio
from typing import Optional, List, Dict, Any
import asyncpg
from asyncpg.pool import Pool
from contextlib import asynccontextmanager

from chatbot.config.settings import settings
from chatbot.utils.logger import get_logger

logger = get_logger(__name__)


class PostgreSQLClient:
    """PostgreSQL client with connection pooling"""

    def __init__(self):
        self.pool: Optional[Pool] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        """Initialize connection pool"""
        if self.pool is not None:
            return

        async with self._lock:
            if self.pool is not None:
                return

            try:
                self.pool = await asyncpg.create_pool(
                    host=settings.POSTGRES_HOST,
                    port=settings.POSTGRES_PORT,
                    user=settings.POSTGRES_USER,
                    password=settings.POSTGRES_PASSWORD,
                    database=settings.POSTGRES_DATABASE,
                    min_size=5,
                    max_size=20,
                    command_timeout=60,
                    server_settings={
                        'application_name': 'chatbot',
                        'jit': 'off'  # Disable JIT for faster simple queries
                    }
                )
                logger.info("✅ PostgreSQL connection pool created")
            except Exception as e:
                logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
                raise

    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("PostgreSQL connection pool closed")

    @asynccontextmanager
    async def acquire(self):
        """Acquire connection from pool"""
        if self.pool is None:
            await self.connect()

        async with self.pool.acquire() as connection:
            yield connection

    async def execute(self, query: str, *args) -> str:
        """Execute query without returning results"""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple rows"""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch single row"""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch single value"""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)


# Global instance
pg_client = PostgreSQLClient()


async def get_postgres_client() -> PostgreSQLClient:
    """Dependency injection for FastAPI"""
    if pg_client.pool is None:
        await pg_client.connect()
    return pg_client
```

#### 3.2 pgvector Integration

**File**: `chatbot/services/retrieval/pgvector_retriever.py`

```python
"""
Dynamic content retrieval using pgvector
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import numpy as np

from chatbot.integrations.postgres.client import pg_client
from chatbot.services.embedding.embedding_service import EmbeddingService
from chatbot.utils.logger import get_logger

logger = get_logger(__name__)


class PgVectorRetriever:
    """Retrieve dynamic content using pgvector"""

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service

    async def store_embedding(
        self,
        content_type: str,
        content_id: str,
        content_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_hours: Optional[int] = 168  # 7 days default
    ) -> str:
        """Store embedding in PostgreSQL"""
        try:
            # Generate embedding
            embedding = await self.embedding_service.embed_text(content_text)

            # Calculate expiration
            expires_at = None
            if ttl_hours:
                expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

            # Store in database
            embedding_id = await pg_client.fetchval("""
                INSERT INTO embeddings (content_type, content_id, content_text, embedding, metadata, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, content_type, content_id, content_text, embedding, metadata or {}, expires_at)

            logger.info(f"✅ Stored embedding: {content_type}:{content_id}")
            return str(embedding_id)

        except Exception as e:
            logger.error(f"❌ Failed to store embedding: {e}")
            raise

    async def search_similar(
        self,
        query: str,
        content_type: Optional[str] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for similar embeddings using cosine similarity"""
        try:
            # Generate query embedding
            query_embedding = await self.embedding_service.embed_text(query)

            # Build query
            where_clause = "WHERE (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)"
            params = [query_embedding, top_k]
            param_idx = 3

            if content_type:
                where_clause += f" AND content_type = ${param_idx}"
                params.append(content_type)
                param_idx += 1

            sql = f"""
                SELECT
                    id,
                    content_type,
                    content_id,
                    content_text,
                    metadata,
                    1 - (embedding <=> $1) as similarity,
                    created_at
                FROM embeddings
                {where_clause}
                ORDER BY embedding <=> $1
                LIMIT $2
            """

            # Execute search
            results = await pg_client.fetch(sql, *params)

            # Filter by threshold and format
            matches = []
            for row in results:
                similarity = float(row['similarity'])
                if similarity >= similarity_threshold:
                    matches.append({
                        'id': str(row['id']),
                        'content_type': row['content_type'],
                        'content_id': row['content_id'],
                        'content_text': row['content_text'],
                        'metadata': row['metadata'],
                        'similarity': similarity,
                        'created_at': row['created_at']
                    })

            logger.info(f"🔍 Found {len(matches)} similar embeddings (threshold: {similarity_threshold})")
            return matches

        except Exception as e:
            logger.error(f"❌ Vector search failed: {e}")
            return []

    async def get_by_content_id(self, content_id: str) -> Optional[Dict[str, Any]]:
        """Get embedding by content ID"""
        try:
            row = await pg_client.fetchrow("""
                SELECT id, content_type, content_id, content_text, metadata, created_at
                FROM embeddings
                WHERE content_id = $1
                  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                LIMIT 1
            """, content_id)

            if row:
                return {
                    'id': str(row['id']),
                    'content_type': row['content_type'],
                    'content_id': row['content_id'],
                    'content_text': row['content_text'],
                    'metadata': row['metadata'],
                    'created_at': row['created_at']
                }
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get embedding: {e}")
            return None

    async def delete_by_content_id(self, content_id: str) -> bool:
        """Delete embeddings by content ID"""
        try:
            result = await pg_client.execute("""
                DELETE FROM embeddings WHERE content_id = $1
            """, content_id)

            deleted = int(result.split()[-1])
            logger.info(f"🗑️  Deleted {deleted} embeddings for content_id: {content_id}")
            return deleted > 0

        except Exception as e:
            logger.error(f"❌ Failed to delete embeddings: {e}")
            return False

    async def cleanup_expired(self) -> int:
        """Remove expired embeddings"""
        try:
            result = await pg_client.execute("""
                DELETE FROM embeddings WHERE expires_at < CURRENT_TIMESTAMP
            """)

            deleted = int(result.split()[-1])
            if deleted > 0:
                logger.info(f"🧹 Cleaned up {deleted} expired embeddings")
            return deleted

        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
            return 0
```

#### 3.3 Update Hybrid Retriever

**File**: `chatbot/services/retrieval/hybrid_retriever.py` (update)

```python
"""
Hybrid retrieval combining FAISS (static KB) and pgvector (dynamic content)
"""
import asyncio
from typing import List, Dict, Any, Optional

from chatbot.services.retrieval.kb_retriever import KBRetriever
from chatbot.services.retrieval.pgvector_retriever import PgVectorRetriever
from chatbot.services.embedding.embedding_service import EmbeddingService
from chatbot.utils.logger import get_logger

logger = get_logger(__name__)


class HybridRetriever:
    """Combines FAISS (static) and pgvector (dynamic) retrieval"""

    def __init__(
        self,
        kb_retriever: KBRetriever,
        embedding_service: EmbeddingService
    ):
        self.kb_retriever = kb_retriever
        self.pgvector_retriever = PgVectorRetriever(embedding_service)

    async def retrieve(
        self,
        query: str,
        include_static: bool = True,
        include_dynamic: bool = True,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Retrieve from both static KB and dynamic embeddings

        Returns:
            {
                'static_chunks': [...],
                'dynamic_chunks': [...],
                'combined_context': "...",
                'sources': [...]
            }
        """
        results = {
            'static_chunks': [],
            'dynamic_chunks': [],
            'combined_context': '',
            'sources': []
        }

        # Retrieve in parallel
        tasks = []
        if include_static:
            tasks.append(self._get_static_chunks(query, top_k))
        if include_dynamic:
            tasks.append(self._get_dynamic_chunks(query, top_k))

        if not tasks:
            return results

        retrieved = await asyncio.gather(*tasks, return_exceptions=True)

        # Process static results
        if include_static:
            static_result = retrieved[0] if not isinstance(retrieved[0], Exception) else None
            if static_result:
                results['static_chunks'] = static_result
                results['sources'].append('static_kb')

        # Process dynamic results
        if include_dynamic:
            dynamic_idx = 1 if include_static else 0
            dynamic_result = retrieved[dynamic_idx] if not isinstance(retrieved[dynamic_idx], Exception) else None
            if dynamic_result:
                results['dynamic_chunks'] = dynamic_result
                results['sources'].append('dynamic_db')

        # Combine context
        results['combined_context'] = self._format_context(
            results['static_chunks'],
            results['dynamic_chunks']
        )

        return results

    async def _get_static_chunks(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """Retrieve from FAISS static KB"""
        try:
            # Use existing KB retriever (FAISS)
            chunks = await asyncio.to_thread(
                self.kb_retriever.retrieve,
                query,
                top_k=top_k
            )
            return chunks
        except Exception as e:
            logger.error(f"❌ Static retrieval failed: {e}")
            return []

    async def _get_dynamic_chunks(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """Retrieve from pgvector dynamic embeddings"""
        try:
            matches = await self.pgvector_retriever.search_similar(
                query,
                content_type='dynamic_url',  # Or None for all types
                top_k=top_k,
                similarity_threshold=0.7
            )
            return matches
        except Exception as e:
            logger.error(f"❌ Dynamic retrieval failed: {e}")
            return []

    def _format_context(
        self,
        static_chunks: List[Dict[str, Any]],
        dynamic_chunks: List[Dict[str, Any]]
    ) -> str:
        """Format retrieved chunks into context string"""
        context_parts = []

        # Add static KB context
        if static_chunks:
            context_parts.append("=== Knowledge Base ===")
            for i, chunk in enumerate(static_chunks[:3], 1):
                text = chunk.get('text', chunk.get('content_text', ''))
                context_parts.append(f"{i}. {text[:500]}")

        # Add dynamic context
        if dynamic_chunks:
            context_parts.append("\n=== Recent Information ===")
            for i, chunk in enumerate(dynamic_chunks[:3], 1):
                text = chunk.get('content_text', '')
                metadata = chunk.get('metadata', {})
                source = metadata.get('source', 'dynamic')
                context_parts.append(f"{i}. [{source}] {text[:500]}")

        return "\n\n".join(context_parts)

    async def store_dynamic_content(
        self,
        content_id: str,
        content_text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Store dynamic content for future retrieval"""
        return await self.pgvector_retriever.store_embedding(
            content_type='dynamic_url',
            content_id=content_id,
            content_text=content_text,
            metadata=metadata,
            ttl_hours=168  # 7 days
        )
```

#### 3.4 Update FAQ Service for PostgreSQL

**File**: `chatbot/database/faq_service.py` (update)

Replace MySQL queries with PostgreSQL:

```python
# Change from mysql.connector to asyncpg
# Example changes:

# OLD (MySQL):
cursor.execute("SELECT * FROM pages WHERE url_pattern LIKE %s", (pattern,))

# NEW (PostgreSQL):
await pg_client.fetch("SELECT * FROM pages WHERE url_pattern LIKE $1", pattern)

# Full-text search:
# OLD:
cursor.execute("SELECT * FROM faq WHERE MATCH(question, keywords) AGAINST (%s)", (query,))

# NEW:
await pg_client.fetch("""
    SELECT * FROM faq
    WHERE to_tsvector('english', question || ' ' || COALESCE(keywords, ''))
          @@ plainto_tsquery('english', $1)
    ORDER BY ts_rank(to_tsvector('english', question), plainto_tsquery('english', $1)) DESC
""", query)
```

---

### Phase 4: Configuration Updates (Week 2)
**Status**: 🟡 Update settings and environment

#### 4.1 Update Settings

**File**: `chatbot/config/settings.py` (add)

```python
# PostgreSQL Configuration
POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_DATABASE: str = os.getenv("POSTGRES_DATABASE", "chatbot")
POSTGRES_POOL_SIZE: int = int(os.getenv("POSTGRES_POOL_SIZE", 10))

# Vector Configuration
VECTOR_DIMENSION: int = int(os.getenv("VECTOR_DIMENSION", 768))  # nomic-embed-text
USE_PGVECTOR: bool = os.getenv("USE_PGVECTOR", "true").lower() == "true"
PGVECTOR_INDEX_TYPE: str = os.getenv("PGVECTOR_INDEX_TYPE", "hnsw")  # hnsw or ivfflat

# Keep existing Redis settings for hot cache
# Keep existing FAISS settings for static KB
```

#### 4.2 Update .env

```bash
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=yourpassword
POSTGRES_DATABASE=chatbot
POSTGRES_POOL_SIZE=10

# Vector Search
VECTOR_DIMENSION=768  # For nomic-embed-text
USE_PGVECTOR=true
PGVECTOR_INDEX_TYPE=hnsw

# Keep existing Redis configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_TTL_DAYS=7

# Keep existing MySQL for gradual migration (optional)
MYSQL_ENABLED=false
```

---

### Phase 5: Testing (Week 3)
**Status**: 🔴 Not started

#### 5.1 Unit Tests

**File**: `tests/test_pgvector_retrieval.py`

```python
import pytest
import asyncio
from chatbot.services.retrieval.pgvector_retriever import PgVectorRetriever
from chatbot.services.embedding.embedding_service import EmbeddingService

@pytest.mark.asyncio
async def test_store_and_retrieve():
    """Test storing and retrieving embeddings"""
    embedding_service = EmbeddingService()
    retriever = PgVectorRetriever(embedding_service)

    # Store test embedding
    content_id = "test_content_123"
    content_text = "Export data for machinery from India to USA"

    embedding_id = await retriever.store_embedding(
        content_type="test",
        content_id=content_id,
        content_text=content_text,
        metadata={"test": True}
    )

    assert embedding_id is not None

    # Search for similar content
    results = await retriever.search_similar(
        query="machinery export from India",
        content_type="test",
        top_k=5
    )

    assert len(results) > 0
    assert results[0]['content_id'] == content_id
    assert results[0]['similarity'] > 0.7

@pytest.mark.asyncio
async def test_hybrid_retrieval():
    """Test hybrid FAISS + pgvector retrieval"""
    from chatbot.services.retrieval.hybrid_retriever import HybridRetriever
    from chatbot.services.retrieval.kb_retriever import KBRetriever

    kb_retriever = KBRetriever()
    embedding_service = EmbeddingService()
    hybrid = HybridRetriever(kb_retriever, embedding_service)

    results = await hybrid.retrieve(
        query="What are HS codes?",
        include_static=True,
        include_dynamic=True,
        top_k=5
    )

    assert 'static_chunks' in results
    assert 'dynamic_chunks' in results
    assert 'combined_context' in results
    assert len(results['sources']) > 0
```

#### 5.2 Performance Benchmarks

**File**: `tests/benchmark_vector_search.py`

```python
import asyncio
import time
from statistics import mean, median

from chatbot.services.retrieval.kb_retriever import KBRetriever
from chatbot.services.retrieval.pgvector_retriever import PgVectorRetriever
from chatbot.services.embedding.embedding_service import EmbeddingService

async def benchmark_faiss():
    """Benchmark FAISS retrieval"""
    kb_retriever = KBRetriever()
    queries = [
        "What are HS codes?",
        "How to export machinery?",
        "India export statistics",
        "Customs duty calculation",
        "Trade data license"
    ]

    times = []
    for query in queries * 10:  # 50 queries total
        start = time.perf_counter()
        await asyncio.to_thread(kb_retriever.retrieve, query, top_k=5)
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)  # Convert to ms

    print(f"FAISS - Mean: {mean(times):.2f}ms, Median: {median(times):.2f}ms, "
          f"Min: {min(times):.2f}ms, Max: {max(times):.2f}ms")

async def benchmark_pgvector():
    """Benchmark pgvector retrieval"""
    embedding_service = EmbeddingService()
    retriever = PgVectorRetriever(embedding_service)

    queries = [
        "What are HS codes?",
        "How to export machinery?",
        "India export statistics",
        "Customs duty calculation",
        "Trade data license"
    ]

    times = []
    for query in queries * 10:  # 50 queries total
        start = time.perf_counter()
        await retriever.search_similar(query, top_k=5)
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)

    print(f"pgvector - Mean: {mean(times):.2f}ms, Median: {median(times):.2f}ms, "
          f"Min: {min(times):.2f}ms, Max: {max(times):.2f}ms")

if __name__ == "__main__":
    print("🏃 Running benchmarks...")
    asyncio.run(benchmark_faiss())
    asyncio.run(benchmark_pgvector())
```

---

### Phase 6: Deployment (Week 3)
**Status**: 🔴 Not started

#### 6.1 Docker Compose Setup

**File**: `docker-compose.yml`

```yaml
version: '3.8'

services:
  postgres:
    image: ankane/pgvector:latest
    container_name: chatbot-postgres
    environment:
      POSTGRES_DB: chatbot
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./chatbot/database/postgres_schema.sql:/docker-entrypoint-initdb.d/01-schema.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: chatbot-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  chatbot:
    build: .
    container_name: chatbot-api
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DATABASE: chatbot
      REDIS_HOST: redis
      REDIS_PORT: 6379
    ports:
      - "8000:8000"
    volumes:
      - ./chatbot:/app/chatbot
      - ./data:/app/data
    command: uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000

volumes:
  postgres_data:
  redis_data:
```

#### 6.2 Backup Strategy

**Script**: `scripts/backup_postgres.sh`

```bash
#!/bin/bash
# Daily PostgreSQL backup

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/postgres"
mkdir -p $BACKUP_DIR

# Full database backup
pg_dump -h localhost -U postgres -d chatbot \
    -F c -b -v -f "$BACKUP_DIR/chatbot_$DATE.backup"

# Backup embeddings separately (they're large)
pg_dump -h localhost -U postgres -d chatbot \
    -t embeddings -F c -b -v -f "$BACKUP_DIR/embeddings_$DATE.backup"

# Keep last 7 days
find $BACKUP_DIR -name "*.backup" -mtime +7 -delete

echo "✅ Backup complete: chatbot_$DATE.backup"
```

---

## Migration Checklist

### Pre-Migration
- [ ] Backup all MySQL data
- [ ] Backup FAISS indices and chunks
- [ ] Document current API endpoints
- [ ] Create test environment
- [ ] Review PostgreSQL requirements (disk space, memory)

### Phase 1: Setup
- [ ] Install PostgreSQL 16+
- [ ] Install pgvector extension
- [ ] Create database and users
- [ ] Test connection from application
- [ ] Set up monitoring (pg_stat_statements)

### Phase 2: Schema
- [ ] Run postgres_schema.sql
- [ ] Verify all tables created
- [ ] Test indexes
- [ ] Run migration script (migrate_mysql_to_postgres.py)
- [ ] Verify data integrity

### Phase 3: Code
- [ ] Implement PostgreSQL client
- [ ] Implement pgvector retriever
- [ ] Update hybrid retriever
- [ ] Update FAQ service
- [ ] Update FastAPI dependencies

### Phase 4: Configuration
- [ ] Update .env files
- [ ] Update settings.py
- [ ] Configure connection pools
- [ ] Test all environment variables

### Phase 5: Testing
- [ ] Unit tests for pgvector
- [ ] Integration tests for hybrid retrieval
- [ ] Performance benchmarks
- [ ] Load testing
- [ ] Verify Redis still works

### Phase 6: Deployment
- [ ] Deploy to staging
- [ ] Monitor for 48 hours
- [ ] Run performance tests
- [ ] Deploy to production
- [ ] Monitor for 1 week
- [ ] Deprecate MySQL

---

## Performance Expectations

| Metric | Current (MySQL + FAISS) | After (PostgreSQL + FAISS + pgvector) |
|--------|------------------------|---------------------------------------|
| Static KB query | <100ms | <100ms (no change) |
| Dynamic query | N/A | 200-500ms |
| FAQ lookup | <50ms | <50ms (same or better) |
| Session load | 10-20ms | 10-20ms (no change) |
| Memory usage | ~2GB | ~4GB (with pgvector) |
| Disk usage | ~500MB | ~20GB (with embeddings) |

---

## Rollback Plan

If issues occur:

1. **Switch back to MySQL** for FAQ:
   ```python
   # In settings.py
   USE_MYSQL = True
   USE_POSTGRES = False
   ```

2. **Disable pgvector** for dynamic content:
   ```python
   USE_PGVECTOR = False
   # Falls back to Redis-only storage
   ```

3. **Keep FAISS** (no changes needed)

4. **Database restore**:
   ```bash
   pg_restore -h localhost -U postgres -d chatbot chatbot_backup.backup
   ```

---

## Cost Analysis

| Component | Current | After Migration | Change |
|-----------|---------|----------------|--------|
| Database | MySQL (free) | PostgreSQL (free) | ✅ Same |
| Vector store | FAISS (free) | FAISS + pgvector (free) | ✅ Same |
| Cache | Redis (free) | Redis (free) | ✅ Same |
| Storage | ~500MB | ~20GB | ⚠️ +19.5GB |
| Memory | ~2GB | ~4GB | ⚠️ +2GB |
| **Total** | **Free** | **Free** | **✅ Still free** |

---

## Conclusion

This hybrid approach gives you:

1. ⚡ **Speed of FAISS** for static KB (no change)
2. 🔍 **Flexibility of pgvector** for dynamic content
3. 🗄️ **Single database** (PostgreSQL instead of MySQL)
4. 💾 **Redis hot cache** for performance (no change)
5. 📈 **Ready to scale** to millions of embeddings
6. 🆓 **Still free and open-source**

**Recommended timeline**: 3 weeks with testing
**Risk level**: Low (incremental migration, easy rollback)
**Performance impact**: Minimal (<10% for dynamic queries)
