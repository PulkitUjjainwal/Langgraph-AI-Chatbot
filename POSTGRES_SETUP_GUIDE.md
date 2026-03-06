# PostgreSQL Setup & Verification Guide

## ✅ Implementation Status

Your PostgreSQL implementation is complete! All components are ready:

- ✅ PostgreSQL client with connection pooling
- ✅ pgvector retriever for dynamic embeddings
- ✅ Conversation and message persistence
- ✅ FAQ service (PostgreSQL)
- ✅ Hybrid retriever (FAISS + pgvector)
- ✅ FastAPI integration
- ✅ Database schema with partitioning
- ✅ Migration scripts
- ✅ Docker Compose configuration

## 🚀 Quick Start

### Option 1: Docker (Recommended)

1. **Install Docker Desktop**
   - Download from: https://www.docker.com/products/docker-desktop/
   - Install and start Docker Desktop

2. **Start PostgreSQL + Redis**
   ```bash
   docker-compose up -d postgres redis
   ```

   Or use the provided script:
   ```cmd
   scripts\setup_postgres_docker.bat
   ```

3. **Verify containers are running**
   ```bash
   docker ps
   ```

   You should see:
   - `chatbot-postgres` (PostgreSQL with pgvector)
   - `chatbot-redis` (Redis cache)

4. **Check PostgreSQL logs**
   ```bash
   docker logs chatbot-postgres
   ```

   Look for: "database system is ready to accept connections"

### Option 2: Local PostgreSQL

1. **Install PostgreSQL**
   - Download from: https://www.postgresql.org/download/windows/
   - Version 14+ recommended

2. **Install pgvector extension**
   - Download from: https://github.com/pgvector/pgvector
   - Or use: `https://github.com/pgvector/pgvector/releases`

3. **Create database**
   ```bash
   psql -U postgres
   ```

   Then run:
   ```sql
   CREATE DATABASE chatbot;
   CREATE EXTENSION vector;
   \q
   ```

4. **Run schema**
   ```cmd
   scripts\run_schema.bat
   ```

   Or manually:
   ```bash
   psql -U postgres -d chatbot -f chatbot\database\postgres_schema.sql
   ```

## 🔧 Configuration

Verify your `.env` file has these settings:

```env
# PostgreSQL Configuration
POSTGRES_ENABLED=true
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=yourpassword
POSTGRES_DATABASE=chatbot

# Connection Pool
POSTGRES_POOL_MIN_SIZE=5
POSTGRES_POOL_MAX_SIZE=20

# Vector Search (pgvector)
VECTOR_DIMENSION=768
USE_PGVECTOR=true
PGVECTOR_INDEX_TYPE=hnsw
EMBEDDING_TTL_HOURS=168
SIMILARITY_THRESHOLD=0.7
```

## ✅ Verify Installation

Run the integration test script:

```bash
python test_postgres_integration.py
```

This will test:
1. ✅ PostgreSQL connection
2. ✅ pgvector extension
3. ✅ Conversation & message persistence
4. ✅ Vector embeddings
5. ✅ FAQ service
6. ✅ Database statistics

Expected output:
```
Testing: PostgreSQL Connection
✅ Connected to PostgreSQL
✅ Database health: healthy
ℹ️  PostgreSQL version: 15.x
✅ pgvector extension installed

Testing: Conversation & Message Persistence
✅ Created conversation: <uuid>
✅ Stored user message
✅ Stored assistant message
✅ Retrieved 2 messages

Testing: pgvector Embeddings
✅ Stored embedding: <uuid>
✅ Found 1 similar embeddings

Testing: FAQ Service (PostgreSQL)
⚠️  No FAQs found (database might be empty)

Testing: Database Statistics
✅ Retrieved database statistics

Test Summary
==========================================
connection          : ✅ PASS
conversations       : ✅ PASS
pgvector            : ✅ PASS
faq                 : ✅ PASS
stats               : ✅ PASS

🎉 All tests passed! PostgreSQL integration is working perfectly!
```

## 📊 Migrate Data from MySQL (Optional)

If you have existing MySQL data to migrate:

```bash
python scripts/migrate_mysql_to_postgres.py
```

This will migrate:
- Pages
- FAQ entries
- User data (if any)

## 🔍 Troubleshooting

### Docker Issues

**Issue:** Docker Desktop not running
```
failed to connect to the docker API
```

**Solution:**
1. Install Docker Desktop from https://www.docker.com/products/docker-desktop/
2. Start Docker Desktop
3. Run `docker ps` to verify it's working

---

**Issue:** Port 5432 already in use
```
Error starting userland proxy: listen tcp4 0.0.0.0:5432: bind: address already in use
```

**Solution:**
- Change port in `.env`: `POSTGRES_PORT=5433`
- Update `docker-compose.yml` port mapping
- Or stop local PostgreSQL: `net stop postgresql-x64-15`

---

### Connection Issues

**Issue:** Connection refused
```
Failed to connect to PostgreSQL: connection refused
```

**Solution:**
1. Check PostgreSQL is running:
   ```bash
   docker ps | grep postgres
   # or
   pg_isready
   ```

2. Verify `.env` settings:
   - `POSTGRES_ENABLED=true`
   - `POSTGRES_HOST=localhost` (or `postgres` for Docker)
   - `POSTGRES_PORT=5432`

3. Check firewall isn't blocking port 5432

---

**Issue:** Authentication failed
```
PostgreSQL authentication failed
```

**Solution:**
1. Verify password in `.env` matches Docker Compose:
   - `.env`: `POSTGRES_PASSWORD=yourpassword`
   - `docker-compose.yml`: Check `POSTGRES_PASSWORD`

2. Reset password (Docker):
   ```bash
   docker-compose down
   docker volume rm scrapper_function_postgres_data
   docker-compose up -d postgres
   ```

---

### pgvector Issues

**Issue:** pgvector extension not found
```
pgvector extension NOT installed
```

**Solution (Docker):**
```bash
docker exec -it chatbot-postgres psql -U postgres -d chatbot
```

Then run:
```sql
CREATE EXTENSION vector;
\q
```

**Solution (Local):**
1. Install pgvector from: https://github.com/pgvector/pgvector
2. Restart PostgreSQL
3. Run: `CREATE EXTENSION vector;`

---

## 🎯 Next Steps

1. ✅ **Verify everything works**
   ```bash
   python test_postgres_integration.py
   ```

2. ✅ **Start the chatbot**
   ```bash
   # Development
   START_SERVER.bat

   # Or directly
   uvicorn fastapi_chatbot:app --reload --host 0.0.0.0 --port 8000
   ```

3. ✅ **Access admin endpoints**
   - Health: http://localhost:8000/api/health/postgres
   - Stats: http://localhost:8000/api/stats/database
   - Conversations: http://localhost:8000/api/admin/conversations/active

4. ✅ **Optional: Access pgAdmin**
   ```bash
   docker-compose --profile admin up -d pgadmin
   ```

   Then visit: http://localhost:5050
   - Email: admin@chatbot.local
   - Password: admin

## 📈 Performance Tuning

Your PostgreSQL is already optimized with:

- ✅ Connection pooling (5-20 connections)
- ✅ HNSW vector index (fast similarity search)
- ✅ Table partitioning by month
- ✅ Full-text search indexes
- ✅ SSD-optimized settings

For production:
- Increase `POSTGRES_POOL_MAX_SIZE` based on load
- Add more monthly partitions as needed
- Run cleanup job: `python -c "from chatbot.services.retrieval.pgvector_retriever import get_pgvector_retriever; import asyncio; asyncio.run(get_pgvector_retriever().cleanup_expired())"`

## 🎉 Success!

If all tests pass, your PostgreSQL implementation is working perfectly!

You now have:
- ✅ Persistent conversation history
- ✅ Dynamic content embeddings with TTL
- ✅ Fast vector search (pgvector)
- ✅ FAQ system
- ✅ Analytics and reporting
- ✅ Production-ready architecture

Happy coding! 🚀
