# FastAPI PostgreSQL Integration - Simple Patch

This file shows you **exactly** what to add to `fastapi_chatbot.py` to enable PostgreSQL support.

## ⚠️ BEFORE YOU START

1. **Backup your current `fastapi_chatbot.py`**:
   ```bash
   copy fastapi_chatbot.py fastapi_chatbot.py.backup
   ```

2. **Ensure PostgreSQL is running**:
   ```bash
   scripts\setup_postgres_docker.bat
   scripts\run_schema.bat
   ```

3. **Update `.env` file** with PostgreSQL settings

---

## 📝 **Changes Required: 4 Simple Steps**

### **Step 1: Add Import at Top** (Line ~100, after existing imports)

Find this section (around line 100):
```python
# Import modular components for prompt building
from chatbot.services.agent.prompts import PromptBuilder, PromptConfig
```

**ADD THESE LINES AFTER IT:**
```python
# PostgreSQL Integration
from chatbot.integrations.postgres.fastapi_integration import (
    init_postgres_in_ensure_initialized,
    store_chat_interaction,
    store_dynamic_content_in_pgvector,
    add_postgres_to_router,
    shutdown_postgres
)
```

---

### **Step 2: Add PostgreSQL Initialization** (Line ~3350, in `ensure_initialized()` function)

Find the `ensure_initialized()` function (around line 3308):
```python
async def ensure_initialized():
    """Lazy initialization on first request"""
    global chatbot_manager, redis_manager, hostility_detector, lead_manager, credit_manager, slot_manager, faq_service, _initialization_lock, app_start_time

    if chatbot_manager is not None:
        return  # Already initialized
```

**ADD THIS LINE** before the `if chatbot_manager is not None:` check (after the lock is acquired):
```python
async def ensure_initialized():
    """Lazy initialization on first request"""
    global chatbot_manager, redis_manager, hostility_detector, lead_manager, credit_manager, slot_manager, faq_service, _initialization_lock, app_start_time

    # Initialize PostgreSQL (NEW - ADD THIS)
    await init_postgres_in_ensure_initialized()

    if chatbot_manager is not None:
        return  # Already initialized
```

---

### **Step 3: Store Chat Interactions** (Line ~3600, in `/chat` endpoint)

Find where the chat response is generated (around line 3580):
```python
        response, processing_time, sources_used = await asyncio.wait_for(
            chatbot_manager.chat(
                message=request.message,
                session_id=request.session_id,
                dynamic_url=request.dynamic_url
            ),
            timeout=90.0
        )
```

**ADD THESE LINES AFTER getting the response:**
```python
        response, processing_time, sources_used = await asyncio.wait_for(
            chatbot_manager.chat(
                message=request.message,
                session_id=request.session_id,
                dynamic_url=request.dynamic_url
            ),
            timeout=90.0
        )

        # Store chat interaction in PostgreSQL (NEW - ADD THIS)
        await store_chat_interaction(
            session_id=request.session_id,
            user_message=request.message,
            assistant_response=response,
            metadata={
                "processing_time_ms": processing_time * 1000,
                "sources_used": sources_used,
                "dynamic_url": request.dynamic_url
            }
        )
```

---

### **Step 4: Add PostgreSQL Routes** (Line ~3550, after router creation)

Find where the router is created (around line 3549):
```python
# Create API router with /api prefix
router = APIRouter(prefix="/api")
```

**ADD THIS LINE AFTER IT:**
```python
# Create API router with /api prefix
router = APIRouter(prefix="/api")

# Add PostgreSQL health and admin routes (NEW - ADD THIS)
add_postgres_to_router(router)
```

---

## ✅ **That's It! Only 4 Changes**

### **Summary:**
1. ✅ Added imports (1 block, 7 lines)
2. ✅ Added PostgreSQL init (1 line)
3. ✅ Added chat storage (1 block, 10 lines)
4. ✅ Added admin routes (1 line)

**Total changes: ~20 lines of code**

---

## 🧪 **Testing Your Integration**

### **1. Start Your Application**
```bash
uvicorn fastapi_chatbot:app --reload
```

**Look for this in the startup logs:**
```
[INFO] 🚀 Starting PostgreSQL stack...
[INFO] ✅ PostgreSQL connection pool created (min=5, max=20)
[INFO] ✅ FAQ Service initialized
[INFO] ✅ Conversation Service initialized
[INFO] ✅ Message Service initialized
[INFO] ✅ PostgreSQL stack initialized successfully
```

### **2. Check Health Endpoint**
```bash
curl http://localhost:8000/api/health/postgres
```

**Expected Response:**
```json
{
  "status": "healthy",
  "postgres": {
    "status": "healthy",
    "pool_size": 10,
    "pool_available": 9,
    "version": "16.1",
    "pgvector_installed": true
  },
  "pgvector_enabled": true
}
```

### **3. Send a Test Message**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are HS codes?",
    "session_id": "test_session_123"
  }'
```

### **4. Check If Message Was Stored**
```bash
curl http://localhost:8000/api/admin/conversation/test_session_123/messages
```

**Expected Response:**
```json
{
  "session_id": "test_session_123",
  "conversation": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "session_id": "test_session_123",
    "site_id": "exportgenius",
    "started_at": "2026-03-05T10:30:00",
    "is_active": true
  },
  "messages": [
    {
      "id": "...",
      "role": "user",
      "content": "What are HS codes?",
      "created_at": "2026-03-05T10:30:01"
    },
    {
      "id": "...",
      "role": "assistant",
      "content": "HS codes are...",
      "created_at": "2026-03-05T10:30:05"
    }
  ],
  "count": 2
}
```

### **5. Check Database Stats**
```bash
curl http://localhost:8000/api/stats/database
```

---

## 🔧 **Troubleshooting**

### **Problem: Import Error**

**Error:**
```
ModuleNotFoundError: No module named 'chatbot.integrations.postgres.fastapi_integration'
```

**Solution:**
```bash
# Make sure you're in the project directory
cd "C:\MI Ticket\MI Chat Bot\Scrapper Function"

# Verify file exists
dir chatbot\integrations\postgres\fastapi_integration.py

# If missing, the file wasn't created. Check previous steps.
```

---

### **Problem: PostgreSQL Not Connecting**

**Logs show:**
```
[WARNING] PostgreSQL initialization failed: connection refused
```

**Solution:**
```bash
# Check if PostgreSQL container is running
docker ps | findstr chatbot-postgres

# If not running, start it
docker start chatbot-postgres

# Or run setup again
scripts\setup_postgres_docker.bat
```

---

### **Problem: Tables Not Found**

**Error:**
```
asyncpg.exceptions.UndefinedTableError: relation "conversations" does not exist
```

**Solution:**
```bash
# Run schema creation
scripts\run_schema.bat

# Or manually
docker exec -i chatbot-postgres psql -U postgres -d chatbot < chatbot\database\postgres_schema.sql
```

---

### **Problem: Messages Not Being Stored**

**Symptom:** Health check passes but messages don't appear in database

**Debug:**
1. Check logs for errors:
   ```python
   # In terminal where app is running, look for:
   [ERROR] Failed to store chat interaction: ...
   ```

2. Check if PostgreSQL is enabled:
   ```bash
   # In .env file
   POSTGRES_ENABLED=true  # Must be true
   ```

3. Test database connection manually:
   ```bash
   docker exec -it chatbot-postgres psql -U postgres -d chatbot

   # In psql:
   SELECT COUNT(*) FROM messages;
   \q
   ```

---

### **Problem: App Won't Start**

**Error:**
```
NameError: name 'init_postgres_in_ensure_initialized' is not defined
```

**Solution:** You forgot Step 1 (add imports). Go back and add the import statement.

---

## 🚀 **Advanced: Optional Enhancements**

### **Store Dynamic Content in pgvector**

If you fetch dynamic content (e.g., company data from API), you can store it in pgvector for persistent retrieval.

Find where dynamic content is fetched in your code, and add:
```python
# After fetching dynamic content from API
if dynamic_content and settings.use_pgvector:
    # Store in pgvector for future retrieval (persists beyond session)
    await store_dynamic_content_in_pgvector(
        content_id=f"company_{company_id}",
        content_text=dynamic_content,
        metadata={
            "source": "export_genius_api",
            "company_id": company_id,
            "fetched_at": datetime.utcnow().isoformat()
        },
        ttl_hours=168  # 7 days
    )
```

---

### **Update Hybrid Retriever for pgvector**

If you want to retrieve from pgvector in addition to FAISS and Redis:

Find where `hybrid_retriever.hybrid_retrieve()` is called and update to use the new `hybrid_retrieve_v2()`:

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
    dynamic_top_k=3,      # Redis hot cache
    pgvector_top_k=2,     # pgvector persistent
    use_redis=True,
    use_pgvector=True     # Enable pgvector retrieval
)

# Access combined context
combined_context = retrieval_result['combined_context']
sources = retrieval_result['sources']  # ['static_kb', 'redis_cache', 'pgvector']
```

---

## 📊 **Monitoring Your Database**

### **Check Table Sizes**
```bash
docker exec chatbot-postgres psql -U postgres -d chatbot -c "
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

### **Count Messages**
```bash
docker exec chatbot-postgres psql -U postgres -d chatbot -c "
SELECT COUNT(*) as total_messages FROM messages;
"
```

### **Active Conversations**
```bash
docker exec chatbot-postgres psql -U postgres -d chatbot -c "
SELECT COUNT(*) as active_conversations
FROM conversations
WHERE is_active = TRUE;
"
```

---

## 🎯 **What You Get After Integration**

### **New Endpoints Available:**

1. **Health Check**
   ```
   GET /api/health/postgres
   ```

2. **Database Statistics**
   ```
   GET /api/stats/database
   ```

3. **Active Conversations**
   ```
   GET /api/admin/conversations/active?site_id=exportgenius&limit=100
   ```

4. **Conversation Messages**
   ```
   GET /api/admin/conversation/{session_id}/messages?limit=50
   ```

5. **Cleanup Expired Embeddings**
   ```
   POST /api/admin/embeddings/cleanup
   ```

### **Features Unlocked:**

✅ **All conversations stored** in PostgreSQL (never lose chat history)
✅ **Message search** by content, role, date
✅ **Persistent embeddings** with pgvector (dynamic content cached long-term)
✅ **Analytics** on user behavior, popular questions, response times
✅ **Full-text FAQ search** in PostgreSQL (better than MySQL)
✅ **Auto-partitioning** by month (scales to millions of messages)
✅ **Health monitoring** endpoints (know when things break)
✅ **Graceful degradation** (works without PostgreSQL if needed)

---

## 🔄 **Rollback Instructions**

If something goes wrong and you need to rollback:

1. **Restore backup:**
   ```bash
   copy fastapi_chatbot.py.backup fastapi_chatbot.py
   ```

2. **Or disable PostgreSQL:**
   ```bash
   # In .env file
   POSTGRES_ENABLED=false
   USE_PGVECTOR=false
   ```

3. **Restart application:**
   ```bash
   uvicorn fastapi_chatbot:app --reload
   ```

App will continue working in Redis-only mode (no PostgreSQL storage).

---

## 📚 **Next Steps**

After successful integration:

1. ✅ **Test with real users** - Monitor `/api/stats/database` endpoint
2. 📊 **Set up monitoring** - Use `/api/health/postgres` for health checks
3. 🔄 **Migrate old data** - Run `python scripts/migrate_mysql_to_postgres.py`
4. 🧪 **Run tests** - `pytest tests/test_postgres_integration.py`
5. 🚀 **Deploy to production** - Use Docker Compose (see next file)

---

## ✅ **Verification Checklist**

- [ ] Backup created (`fastapi_chatbot.py.backup`)
- [ ] PostgreSQL running (`docker ps | findstr chatbot-postgres`)
- [ ] Schema created (`scripts\run_schema.bat`)
- [ ] `.env` updated with PostgreSQL settings
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Imports added (Step 1)
- [ ] PostgreSQL init added (Step 2)
- [ ] Chat storage added (Step 3)
- [ ] Routes added (Step 4)
- [ ] App starts without errors
- [ ] Health endpoint returns "healthy"
- [ ] Test message stored in database
- [ ] Admin endpoints working

---

**Integration Complete! Your chatbot now has PostgreSQL superpowers! 🎉**
