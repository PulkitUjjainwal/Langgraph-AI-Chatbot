# FastAPI PostgreSQL Integration Guide

This guide shows you how to integrate PostgreSQL + pgvector into your existing FastAPI application.

## Step 1: Add Startup/Shutdown Hooks

Open `fastapi_chatbot.py` and add the following imports at the top:

```python
# Add these imports after your existing imports
from chatbot.integrations.postgres.startup import (
    startup_postgres_stack,
    shutdown_postgres_stack,
    add_postgres_routes
)
```

## Step 2: Update Startup Event

Find your existing startup event handler and add PostgreSQL initialization:

```python
@app.on_event("startup")
async def startup_event():
    """Application startup"""
    logger.info("🚀 Starting MI Chat Bot API...")

    # Your existing startup code...
    # (Redis initialization, etc.)

    # ADD THIS: Initialize PostgreSQL stack
    await startup_postgres_stack()

    logger.info("✅ Application started successfully")
```

## Step 3: Update Shutdown Event

Find your existing shutdown event handler and add PostgreSQL cleanup:

```python
@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown"""
    logger.info("👋 Shutting down MI Chat Bot API...")

    # Your existing shutdown code...

    # ADD THIS: Shutdown PostgreSQL stack
    await shutdown_postgres_stack()

    logger.info("✅ Application shutdown complete")
```

## Step 4: Add Health Check and Admin Routes

After creating your `app = FastAPI()` instance, add the PostgreSQL routes:

```python
app = FastAPI(
    title="MI Chat Bot API",
    version="1.0.0",
    # ... your existing config
)

# ADD THIS: Add PostgreSQL health check and admin routes
add_postgres_routes(app)
```

## Step 5: Update Chat Endpoint to Store Conversations

Find your `/chat` endpoint and add conversation/message persistence:

```python
from chatbot.database.conversation_service import get_conversation_service
from chatbot.database.message_service import get_message_service

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Chat endpoint"""
    try:
        # Your existing code to get user query, session_id, etc.
        user_query = request.query
        session_id = request.session_id or str(uuid.uuid4())

        # ADD THIS: Create/update conversation in PostgreSQL
        conversation_service = await get_conversation_service()
        conversation_id = await conversation_service.create_conversation(
            session_id=session_id,
            site_id=settings.site_id,
            metadata={
                "url": request.current_url,
                "user_agent": request.user_agent,
                "source": "web_widget"
            }
        )

        # ADD THIS: Store user message
        message_service = await get_message_service()
        await message_service.store_message(
            conversation_id=conversation_id,
            role="user",
            content=user_query,
            metadata={"timestamp": datetime.utcnow().isoformat()}
        )

        # Your existing LangGraph/LLM code...
        response = await run_chatbot_workflow(...)

        # ADD THIS: Store assistant response
        await message_service.store_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response,
            metadata={
                "context_sources": ["static_kb", "pgvector"],
                "response_time_ms": elapsed_ms
            }
        )

        # ADD THIS: Update conversation activity
        await conversation_service.update_activity(session_id)

        return {"response": response, "session_id": session_id}

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

## Step 6: Update Retrieval to Use Hybrid (FAISS + pgvector)

Find where you initialize your retrieval system and update to use the enhanced hybrid retriever:

```python
from chatbot.services.retrieval.hybrid_retriever import HybridRetriever
from chatbot.services.retrieval.kb_retriever import KnowledgeBaseRetriever
from chatbot.services.retrieval.pgvector_retriever import get_pgvector_retriever
from chatbot.integrations.redis.client import RedisMemoryManager

# Initialize retrievers
kb_retriever = KnowledgeBaseRetriever()
redis_manager = RedisMemoryManager()

# ADD THIS: Initialize pgvector retriever
pgvector_retriever = get_pgvector_retriever() if settings.use_pgvector else None

# Create hybrid retriever with all three sources
hybrid_retriever = HybridRetriever(
    kb_retriever=kb_retriever,
    redis_manager=redis_manager,
    pgvector_retriever=pgvector_retriever  # ADD THIS
)
```

Then update your retrieval calls to use the enhanced hybrid_retrieve_v2:

```python
# OLD:
kb_context, dynamic_context = await hybrid_retriever.hybrid_retrieve(
    query=user_query,
    session_id=session_id,
    dynamic_url=dynamic_url
)

# NEW:
retrieval_result = await hybrid_retriever.hybrid_retrieve_v2(
    query=user_query,
    session_id=session_id,
    dynamic_url=dynamic_url,
    kb_top_k=3,           # FAISS static KB
    dynamic_top_k=3,      # Redis cache
    pgvector_top_k=2,     # pgvector persistent
    use_redis=True,
    use_pgvector=True
)

# Access results
kb_context = retrieval_result['kb_context']
dynamic_context = retrieval_result['dynamic_context']
pgvector_context = retrieval_result['pgvector_context']
combined_context = retrieval_result['combined_context']  # All sources combined
sources = retrieval_result['sources']  # ['static_kb', 'redis_cache', 'pgvector']
```

## Step 7: Store Dynamic Content in pgvector

When you fetch dynamic content (e.g., from Export Genius API), store it in pgvector for persistent retrieval:

```python
# After fetching dynamic content from API
if dynamic_content and settings.use_pgvector:
    # Store in pgvector for future retrieval
    embedding_id = await hybrid_retriever.store_dynamic_content(
        content_id=f"company_{company_id}",
        content_text=dynamic_content,
        metadata={
            "source": "export_genius_api",
            "company_id": company_id,
            "fetch_date": datetime.utcnow().isoformat()
        },
        ttl_hours=168  # 7 days
    )
    logger.info(f"Stored dynamic content in pgvector: {embedding_id}")
```

## Step 8: Update FAQ Service

Replace the old FAQ service import with the new PostgreSQL-enabled version:

```python
# OLD:
from chatbot.database.faq_service import FAQService

# NEW:
from chatbot.database.faq_service_postgres import get_faq_service

# Usage:
faq_service = await get_faq_service()
suggested_questions = await faq_service.get_suggested_questions(
    url=current_url,
    limit=5
)
```

## Step 9: Add Environment Variables

Ensure your `.env` file has the PostgreSQL configuration:

```bash
# PostgreSQL Configuration
POSTGRES_ENABLED=true
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=yourpassword
POSTGRES_DATABASE=chatbot
POSTGRES_POOL_MIN_SIZE=5
POSTGRES_POOL_MAX_SIZE=20

# Vector Search Configuration
VECTOR_DIMENSION=768
USE_PGVECTOR=true
PGVECTOR_INDEX_TYPE=hnsw
EMBEDDING_TTL_HOURS=168
SIMILARITY_THRESHOLD=0.7

# Keep MySQL enabled during migration (optional)
MYSQL_ENABLED=false
```

## Step 10: Test the Integration

1. **Start PostgreSQL** (if not already running):
   ```bash
   # Using Docker
   docker run -d --name chatbot-postgres \
     -e POSTGRES_PASSWORD=yourpassword \
     -e POSTGRES_DB=chatbot \
     -p 5432:5432 \
     ankane/pgvector:latest

   # Or install locally
   # See: https://www.postgresql.org/download/
   ```

2. **Create database and run schema**:
   ```bash
   psql -U postgres -c "CREATE DATABASE chatbot;"
   psql -U postgres -d chatbot -c "CREATE EXTENSION vector;"
   psql -U postgres -d chatbot -f chatbot/database/postgres_schema.sql
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Start your application**:
   ```bash
   uvicorn fastapi_chatbot:app --reload
   ```

5. **Check health endpoints**:
   ```bash
   # PostgreSQL health
   curl http://localhost:8000/api/health/postgres

   # Database stats
   curl http://localhost:8000/api/stats/database
   ```

## New API Endpoints

After integration, you'll have these new endpoints:

### Health Check
```bash
GET /api/health/postgres
```
Response:
```json
{
  "status": "healthy",
  "postgres": {
    "status": "healthy",
    "pool_size": 10,
    "pool_available": 8,
    "version": "16.1",
    "pgvector_installed": true
  },
  "pgvector_enabled": true
}
```

### Database Statistics
```bash
GET /api/stats/database
```
Response:
```json
{
  "postgres": {
    "database_size": "25 MB",
    "table_sizes": [...],
    "row_counts": {
      "users": 5,
      "conversations": 1234,
      "messages": 5678,
      "embeddings": 890,
      "faq": 50
    }
  },
  "conversations": {
    "total": 1234,
    "active": 45,
    "today": 89,
    "by_site": {
      "exportgenius": 600,
      "marketinside": 634
    }
  },
  "messages": {
    "total": 5678,
    "today": 234,
    "by_role": {
      "user": 2839,
      "assistant": 2839
    },
    "avg_length": 156
  },
  "embeddings": {
    "total_embeddings": 890,
    "by_content_type": {
      "dynamic_url": 850,
      "user_message": 40
    },
    "expired_count": 0
  }
}
```

### Active Conversations
```bash
GET /api/admin/conversations/active?site_id=exportgenius&limit=100
```

### Conversation Messages
```bash
GET /api/admin/conversation/{session_id}/messages?limit=50
```

### Cleanup Expired Embeddings
```bash
POST /api/admin/embeddings/cleanup
```

## Architecture Summary

After integration, your chatbot will use this architecture:

```
User Query
    │
    ├──> FAISS (Static KB)       ──> <100ms, 2,300 chunks
    │
    ├──> Redis (Hot Cache)       ──> Session-specific, 7-day TTL
    │
    └──> pgvector (PostgreSQL)   ──> Persistent, filterable, searchable
            │
            └──> Combined, ranked results

Conversation/Message Flow:
    User Message
        ↓
    Store in PostgreSQL (messages table)
        ↓
    LangGraph Workflow (LLM Response)
        ↓
    Store Response in PostgreSQL
        ↓
    Update Conversation Activity

Dynamic Content Flow:
    API Fetch (Export Genius, etc.)
        ↓
    Store in Redis (hot cache, 7 days)
        ↓
    Store in pgvector (persistent, searchable)
        ↓
    Future queries can retrieve from either
```

## Performance Impact

Expected performance after integration:

| Operation | Before | After | Impact |
|-----------|--------|-------|--------|
| Static KB query | <100ms | <100ms | No change (FAISS) |
| Dynamic query (cached) | 50-100ms | 50-100ms | No change (Redis) |
| Dynamic query (persistent) | N/A | 200-500ms | New feature (pgvector) |
| Message storage | N/A | 10-20ms | New feature |
| Conversation lookup | N/A | 10-20ms | New feature |
| Overall chat response | 2-5s | 2-5s | Minimal impact |

## Rollback Plan

If you encounter issues, you can disable PostgreSQL without breaking the app:

1. **In .env**:
   ```bash
   POSTGRES_ENABLED=false
   USE_PGVECTOR=false
   MYSQL_ENABLED=true  # Fallback to MySQL for FAQ
   ```

2. **Application will gracefully degrade**:
   - FAQ service falls back to MySQL (or LLM-generated questions)
   - Conversations/messages not stored (Redis-only mode)
   - Dynamic content only in Redis (no persistent storage)
   - FAISS static KB continues working

## Troubleshooting

### PostgreSQL Connection Fails

**Error**: `asyncpg.InvalidCatalogNameError: database "chatbot" does not exist`

**Solution**:
```bash
psql -U postgres -c "CREATE DATABASE chatbot;"
```

---

**Error**: `pgvector extension not installed`

**Solution**:
```bash
psql -U postgres -d chatbot -c "CREATE EXTENSION vector;"
```

### Migration Script Fails

**Error**: `DuplicateTableError: table "users" already exists`

**Solution**: Tables already exist, migration successful. Ignore this error.

### Performance Issues

**Problem**: Slow queries on large datasets

**Solution**: Ensure indexes are created:
```sql
-- Check if indexes exist
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- Rebuild indexes if needed
REINDEX TABLE embeddings;
```

## Next Steps

1. ✅ Complete FastAPI integration
2. 🔄 Migrate FAQ data from MySQL: `python scripts/migrate_mysql_to_postgres.py`
3. 🧪 Run tests: `pytest tests/test_postgres_integration.py`
4. 📊 Monitor with `/api/stats/database`
5. 🚀 Deploy to production

## Support

For issues or questions:
- Check logs: Application logs will show PostgreSQL connection status
- Health check: `GET /api/health/postgres`
- Database stats: `GET /api/stats/database`
- GitHub Issues: https://github.com/Export-genius/EG-Chatbot_API/issues
