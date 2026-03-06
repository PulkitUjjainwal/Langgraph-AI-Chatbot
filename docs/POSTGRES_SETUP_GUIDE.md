# PostgreSQL + pgvector Setup Guide

Complete guide to set up PostgreSQL with pgvector extension for the MI Chat Bot.

## Prerequisites

- Windows 10/11
- Docker Desktop (recommended) OR PostgreSQL 16+
- 2GB free disk space
- Admin privileges

---

## Method 1: Docker Setup (Recommended) ⭐

This is the **fastest and easiest** method. Takes ~5 minutes.

### Step 1: Install Docker Desktop

If you don't have Docker installed:

1. Download Docker Desktop: https://www.docker.com/products/docker-desktop
2. Install and restart your computer
3. Start Docker Desktop
4. Verify installation:
   ```bash
   docker --version
   ```

### Step 2: Run Setup Script

We've created an automated setup script for you:

```bash
cd "C:\MI Ticket\MI Chat Bot\Scrapper Function"
scripts\setup_postgres_docker.bat
```

**What this does:**
- Pulls PostgreSQL + pgvector Docker image
- Creates container named `chatbot-postgres`
- Sets up database named `chatbot`
- Enables pgvector extension
- Exposes port 5432

**Connection details:**
```
Host:     localhost
Port:     5432
Database: chatbot
User:     postgres
Password: chatbot_password_123
```

### Step 3: Create Database Schema

Run the schema creation script:

```bash
scripts\run_schema.bat
```

This creates all tables, indexes, functions, and seed data.

### Step 4: Verify Installation

Connect to database:
```bash
docker exec -it chatbot-postgres psql -U postgres -d chatbot
```

Check tables:
```sql
\dt
```

Check pgvector:
```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
```

Exit:
```sql
\q
```

### Step 5: Update Environment Variables

Copy and update your `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and set:
```bash
# PostgreSQL Configuration
POSTGRES_ENABLED=true
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=chatbot_password_123
POSTGRES_DATABASE=chatbot

# Vector Search
USE_PGVECTOR=true
VECTOR_DIMENSION=768
PGVECTOR_INDEX_TYPE=hnsw
EMBEDDING_TTL_HOURS=168
SIMILARITY_THRESHOLD=0.7
```

### Step 6: Install Python Dependencies

```bash
pip install -r requirements.txt
```

You should see:
- `asyncpg==0.29.0` ✓
- `pgvector==0.2.5` ✓
- `psycopg2-binary==2.9.9` ✓

### ✅ Done!

Your PostgreSQL setup is complete. Continue to **Testing** section below.

---

## Method 2: Native Installation (Advanced)

For users who prefer native installation without Docker.

### Step 1: Install PostgreSQL 16

1. Download PostgreSQL 16 from: https://www.postgresql.org/download/windows/
2. Run installer (use Stack Builder for additional components)
3. During installation:
   - Set password for `postgres` user (remember this!)
   - Port: 5432 (default)
   - Locale: Default
4. Add PostgreSQL to PATH:
   ```
   C:\Program Files\PostgreSQL\16\bin
   ```

### Step 2: Install pgvector Extension

**Windows Installation:**

1. Download pgvector from: https://github.com/pgvector/pgvector/releases
2. Extract to PostgreSQL extensions directory:
   ```
   C:\Program Files\PostgreSQL\16\share\extension\
   ```
3. Copy DLL files to:
   ```
   C:\Program Files\PostgreSQL\16\lib\
   ```

**OR use pre-compiled binaries:**

1. Check if pgvector is available via Stack Builder
2. Or use WSL/Linux for easier installation

### Step 3: Create Database

Open Command Prompt as Administrator:

```bash
# Create database
psql -U postgres -c "CREATE DATABASE chatbot;"

# Enable pgvector extension
psql -U postgres -d chatbot -c "CREATE EXTENSION vector;"

# Verify
psql -U postgres -d chatbot -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

### Step 4: Run Schema

```bash
cd "C:\MI Ticket\MI Chat Bot\Scrapper Function"
psql -U postgres -d chatbot -f chatbot\database\postgres_schema.sql
```

### Step 5: Update Environment Variables

Same as Docker method, but use your chosen password:

```bash
POSTGRES_PASSWORD=your_password_here
```

---

## Testing Your Setup

### Test 1: Connection Test

Create a test file `test_connection.py`:

```python
import asyncio
import asyncpg

async def test_connection():
    try:
        conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            user='postgres',
            password='chatbot_password_123',  # Your password
            database='chatbot'
        )

        # Test query
        version = await conn.fetchval('SELECT version()')
        print(f"✅ Connected to PostgreSQL!")
        print(f"Version: {version}")

        # Test pgvector
        has_pgvector = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )

        if has_pgvector:
            print("✅ pgvector extension installed")
        else:
            print("❌ pgvector extension NOT found")

        await conn.close()

    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
```

Run it:
```bash
python test_connection.py
```

Expected output:
```
✅ Connected to PostgreSQL!
Version: PostgreSQL 16.1 ...
✅ pgvector extension installed
```

### Test 2: Vector Search Test

```python
import asyncio
import asyncpg

async def test_vector_search():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='chatbot_password_123',
        database='chatbot'
    )

    try:
        # Insert test embedding
        test_vector = [0.1] * 768  # 768-dimensional vector

        await conn.execute("""
            INSERT INTO embeddings (content_type, content_id, content_text, embedding)
            VALUES ($1, $2, $3, $4::vector)
        """, "test", "test_1", "This is a test", test_vector)

        print("✅ Inserted test embedding")

        # Search
        results = await conn.fetch("""
            SELECT content_text, 1 - (embedding <=> $1::vector) as similarity
            FROM embeddings
            WHERE content_type = 'test'
            ORDER BY embedding <=> $1::vector
            LIMIT 1
        """, test_vector)

        if results:
            print(f"✅ Vector search working!")
            print(f"   Result: {results[0]['content_text']}")
            print(f"   Similarity: {results[0]['similarity']:.4f}")

        # Cleanup
        await conn.execute("DELETE FROM embeddings WHERE content_type = 'test'")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_vector_search())
```

Run it:
```bash
python test_vector_search.py
```

### Test 3: Application Health Check

After integrating with FastAPI (see FASTAPI_INTEGRATION_GUIDE.md):

```bash
# Start your application
uvicorn fastapi_chatbot:app --reload

# In another terminal, test health endpoint
curl http://localhost:8000/api/health/postgres
```

Expected response:
```json
{
  "status": "healthy",
  "postgres": {
    "status": "healthy",
    "pool_size": 10,
    "pool_available": 9,
    "pool_in_use": 1,
    "version": "16.1",
    "pgvector_installed": true
  },
  "pgvector_enabled": true
}
```

---

## Useful Commands

### Docker Commands

```bash
# Start container
docker start chatbot-postgres

# Stop container
docker stop chatbot-postgres

# View logs
docker logs chatbot-postgres

# Connect to database
docker exec -it chatbot-postgres psql -U postgres -d chatbot

# Restart container
docker restart chatbot-postgres

# Remove container (data preserved in volume)
docker rm -f chatbot-postgres

# Remove volume (WARNING: deletes all data)
docker volume rm postgres_data
```

### PostgreSQL Commands

```bash
# Connect via psql
psql -U postgres -d chatbot

# List tables
\dt

# Describe table
\d embeddings

# List indexes
\di

# Check database size
SELECT pg_size_pretty(pg_database_size('chatbot'));

# Check table sizes
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

# Exit
\q
```

### Maintenance Commands

```sql
-- Vacuum database (reclaim space)
VACUUM ANALYZE;

-- Reindex all tables
REINDEX DATABASE chatbot;

-- Refresh materialized views
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_stats;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_faq_performance;

-- Clean up expired embeddings
SELECT cleanup_expired_embeddings();

-- Create next month's partitions
SELECT create_conversation_partition('2026-04-01');
SELECT create_message_partition('2026-04-01');
```

---

## Troubleshooting

### Problem: Docker container won't start

**Error**: `Error starting container: port 5432 already in use`

**Solution**: Another PostgreSQL instance is running
```bash
# Windows: Stop PostgreSQL service
net stop postgresql-x64-16

# Or change Docker port
docker run -d -p 5433:5432 ...  # Use port 5433 instead
```

---

### Problem: pgvector extension not found

**Error**: `ERROR: extension "vector" is not available`

**Solution**: Using wrong image
```bash
# Make sure you're using pgvector image
docker pull ankane/pgvector:latest

# Not the official postgres image
# docker pull postgres  # ❌ This doesn't have pgvector
```

---

### Problem: Permission denied

**Error**: `psql: FATAL: password authentication failed`

**Solution**: Check password
```bash
# Docker: Password is set in container creation
docker exec chatbot-postgres psql -U postgres -c "ALTER USER postgres PASSWORD 'new_password';"

# Update .env with new password
POSTGRES_PASSWORD=new_password
```

---

### Problem: Connection timeout

**Error**: `asyncpg.exceptions.CannotConnectNowError: connection timeout`

**Solution**: PostgreSQL not ready or firewall blocking
```bash
# Wait longer (PostgreSQL takes 10-15 seconds to start)
timeout /t 15

# Check if container is running
docker ps | findstr chatbot-postgres

# Check PostgreSQL logs
docker logs chatbot-postgres

# Test connectivity
telnet localhost 5432
```

---

### Problem: Schema script fails

**Error**: `ERROR: relation "users" already exists`

**Solution**: Tables already exist (this is OK!)
```sql
-- Check existing tables
docker exec chatbot-postgres psql -U postgres -d chatbot -c "\dt"

-- If you want to start fresh (WARNING: deletes all data)
docker exec chatbot-postgres psql -U postgres -d chatbot -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

-- Then run schema again
```

---

### Problem: Python can't connect

**Error**: `ModuleNotFoundError: No module named 'asyncpg'`

**Solution**: Install dependencies
```bash
pip install -r requirements.txt
```

---

**Error**: `asyncpg.exceptions.InvalidPasswordError`

**Solution**: Password mismatch
```python
# Check .env file
POSTGRES_PASSWORD=chatbot_password_123  # Must match Docker container

# Or check settings.py is loading .env correctly
from chatbot.config.settings import get_settings
settings = get_settings()
print(settings.postgres_password)  # Should match .env
```

---

## Backup & Restore

### Backup Database

```bash
# Full backup
docker exec chatbot-postgres pg_dump -U postgres chatbot > backup_$(date +%Y%m%d).sql

# Backup single table
docker exec chatbot-postgres pg_dump -U postgres -t embeddings chatbot > embeddings_backup.sql
```

### Restore Database

```bash
# Restore from backup
docker exec -i chatbot-postgres psql -U postgres chatbot < backup_20260305.sql
```

---

## Performance Tuning

### For Development (default settings are fine)

```sql
-- Current settings
SHOW shared_buffers;
SHOW work_mem;
SHOW maintenance_work_mem;
```

### For Production (adjust based on your server)

Add to Docker run command:
```bash
docker run -d \
  --name chatbot-postgres \
  -e POSTGRES_PASSWORD=yourpassword \
  -e POSTGRES_DB=chatbot \
  -p 5432:5432 \
  --shm-size=1g \
  -v postgres_data:/var/lib/postgresql/data \
  ankane/pgvector:latest \
  -c shared_buffers=1GB \
  -c work_mem=64MB \
  -c maintenance_work_mem=256MB \
  -c effective_cache_size=4GB \
  -c random_page_cost=1.1
```

---

## Security Best Practices

### 1. Change Default Password

```bash
# Generate strong password
openssl rand -base64 32

# Update password
docker exec chatbot-postgres psql -U postgres -c "ALTER USER postgres PASSWORD 'your_strong_password';"

# Update .env
POSTGRES_PASSWORD=your_strong_password
```

### 2. Create Application User (Production)

```sql
-- Connect as postgres
docker exec -it chatbot-postgres psql -U postgres -d chatbot

-- Create app user
CREATE USER chatbot_app WITH PASSWORD 'app_password_here';

-- Grant permissions
GRANT CONNECT ON DATABASE chatbot TO chatbot_app;
GRANT USAGE ON SCHEMA public TO chatbot_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO chatbot_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO chatbot_app;

-- Update .env
POSTGRES_USER=chatbot_app
POSTGRES_PASSWORD=app_password_here
```

### 3. Disable External Access (Production)

```bash
# Only allow localhost
docker run -d \
  --name chatbot-postgres \
  -p 127.0.0.1:5432:5432 \  # Note: 127.0.0.1 instead of 0.0.0.0
  ...
```

---

## Next Steps

✅ PostgreSQL + pgvector installed
✅ Database schema created
✅ Connection tested

**Now:**
1. ✅ PostgreSQL Setup Complete
2. 📝 Follow `FASTAPI_INTEGRATION_GUIDE.md` to integrate with your app
3. 🧪 Run tests: `pytest tests/test_postgres_integration.py`
4. 🚀 Start application: `uvicorn fastapi_chatbot:app --reload`

---

## Support

- PostgreSQL Docs: https://www.postgresql.org/docs/
- pgvector GitHub: https://github.com/pgvector/pgvector
- Docker Desktop: https://docs.docker.com/desktop/
- asyncpg Docs: https://magicstack.github.io/asyncpg/

**Need help?** Check:
1. Docker logs: `docker logs chatbot-postgres`
2. Application logs: Check your FastAPI console output
3. Health endpoint: `curl http://localhost:8000/api/health/postgres`
