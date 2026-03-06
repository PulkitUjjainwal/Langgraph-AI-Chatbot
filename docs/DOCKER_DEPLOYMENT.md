# Docker Compose Deployment Guide

Deploy the entire MI Chat Bot stack (PostgreSQL + Redis + API) with one command.

## 🚀 Quick Start (2 Minutes)

### **1. Create `.env` File**

Copy the example and update values:
```bash
cp .env.example .env
```

**Minimum required settings:**
```bash
# PostgreSQL
POSTGRES_PASSWORD=your_secure_password_here

# API Tokens (if using dynamic content)
EXPORT_GENIUS_BEARER_TOKEN=your_token_here
MARKETINSIDE_BEARER_TOKEN=your_token_here

# Ollama (if running locally)
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

### **2. Start Everything**

```bash
docker-compose up -d
```

**This starts:**
- ✅ PostgreSQL with pgvector
- ✅ Redis for caching
- ✅ Chatbot API

### **3. Verify It's Running**

```bash
# Check containers
docker-compose ps

# Check logs
docker-compose logs -f chatbot

# Test health endpoint
curl http://localhost:8000/api/health
curl http://localhost:8000/api/health/postgres
```

### **4. Test Chat**

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are HS codes?",
    "session_id": "test_123"
  }'
```

---

## 📦 What's Included

### **Services**

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| **postgres** | ankane/pgvector:latest | 5432 | Database + vector search |
| **redis** | redis:7-alpine | 6379 | Caching + checkpoints |
| **chatbot** | Built from Dockerfile | 8000 | FastAPI application |

### **Optional Services** (Admin Tools)

Start with `--profile admin`:
```bash
docker-compose --profile admin up -d
```

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| **pgadmin** | dpage/pgadmin4 | 5050 | PostgreSQL web UI |
| **redis-commander** | rediscommander | 8081 | Redis web UI |

---

## 🔧 Configuration

### **Environment Variables**

All configuration is in `.env` file:

```bash
# API Configuration
API_PORT=8000

# PostgreSQL
POSTGRES_PASSWORD=changeme
POSTGRES_PORT=5432

# Redis
REDIS_PORT=6379

# LLM
OLLAMA_BASE_URL=http://host.docker.internal:11434
EMBEDDING_MODEL=nomic-embed-text
LLM_MODEL=deepseek-v3.1:671b-cloud

# Site
SITE_ID=exportgenius
SITE_NAME=Export Genius

# Security
JWT_SECRET_KEY=CHANGE_ME_IN_PRODUCTION_MIN_32_CHARS
```

### **Volumes**

Data is persisted in Docker volumes:
- `postgres_data` - Database files
- `redis_data` - Redis snapshots
- `pgadmin_data` - pgAdmin settings

---

## 📖 Common Commands

### **Start Services**

```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d postgres

# Start with admin tools
docker-compose --profile admin up -d
```

### **Stop Services**

```bash
# Stop all services
docker-compose stop

# Stop specific service
docker-compose stop chatbot

# Stop and remove containers
docker-compose down
```

### **View Logs**

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f chatbot

# Last 100 lines
docker-compose logs --tail=100 postgres
```

### **Restart Services**

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart chatbot
```

### **Execute Commands**

```bash
# PostgreSQL shell
docker-compose exec postgres psql -U postgres -d chatbot

# Redis CLI
docker-compose exec redis redis-cli

# Application shell
docker-compose exec chatbot bash
```

---

## 🗄️ Database Management

### **Access PostgreSQL**

```bash
# Via Docker
docker-compose exec postgres psql -U postgres -d chatbot

# Via pgAdmin (if admin profile enabled)
# Open browser: http://localhost:5050
# Login: admin@chatbot.local / admin
```

### **Run Migrations**

```bash
# Run schema
docker-compose exec postgres psql -U postgres -d chatbot -f /docker-entrypoint-initdb.d/01-schema.sql

# Or copy and run from host
docker cp chatbot/database/postgres_schema.sql chatbot-postgres:/tmp/
docker-compose exec postgres psql -U postgres -d chatbot -f /tmp/postgres_schema.sql
```

### **Backup Database**

```bash
# Create backup
docker-compose exec postgres pg_dump -U postgres chatbot > backup_$(date +%Y%m%d).sql

# Restore backup
docker-compose exec -T postgres psql -U postgres chatbot < backup_20260305.sql
```

---

## 🔍 Monitoring

### **Health Checks**

```bash
# Application health
curl http://localhost:8000/api/health

# PostgreSQL health
curl http://localhost:8000/api/health/postgres

# Database statistics
curl http://localhost:8000/api/stats/database

# Redis statistics
curl http://localhost:8000/api/redis/stats
```

### **Resource Usage**

```bash
# Container stats
docker stats chatbot-postgres chatbot-redis chatbot-api

# Disk usage
docker system df

# Volume sizes
docker volume ls
docker volume inspect postgres_data
```

### **Container Status**

```bash
# List containers
docker-compose ps

# Detailed info
docker-compose ps -a

# Service logs
docker-compose logs --tail=50 chatbot
```

---

## 🔒 Security Best Practices

### **1. Change Default Passwords**

```bash
# Generate strong password
openssl rand -base64 32

# Update in .env
POSTGRES_PASSWORD=generated_password_here
JWT_SECRET_KEY=another_generated_password_here
```

### **2. Restrict Network Access**

Edit `docker-compose.yml` to bind to localhost only:
```yaml
postgres:
  ports:
    - "127.0.0.1:5432:5432"  # Only localhost

chatbot:
  ports:
    - "127.0.0.1:8000:8000"  # Only localhost
```

### **3. Use Secrets (Production)**

Instead of environment variables:
```yaml
services:
  postgres:
    secrets:
      - postgres_password
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password

secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt
```

---

## 🚀 Production Deployment

### **1. Update docker-compose.prod.yml**

```yaml
version: '3.8'

services:
  postgres:
    restart: always
    mem_limit: 4g
    cpus: 2

  redis:
    restart: always
    mem_limit: 2g
    cpus: 1

  chatbot:
    restart: always
    mem_limit: 2g
    cpus: 2
    environment:
      ENVIRONMENT: production
      LOG_LEVEL: INFO
      DEBUG: "false"
```

### **2. Use Production Env**

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### **3. Set Up Reverse Proxy**

Use nginx or Traefik:
```nginx
server {
    listen 80;
    server_name chatbot.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### **4. Enable SSL**

```bash
# Using Let's Encrypt
certbot --nginx -d chatbot.yourdomain.com
```

---

## 🔄 Updates & Maintenance

### **Update Application**

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose up -d --build chatbot
```

### **Update Database Schema**

```bash
# Copy new schema
docker cp chatbot/database/postgres_schema.sql chatbot-postgres:/tmp/

# Apply changes
docker-compose exec postgres psql -U postgres -d chatbot -f /tmp/postgres_schema.sql
```

### **Update Dependencies**

```bash
# Update requirements.txt
pip freeze > requirements.txt

# Rebuild image
docker-compose build --no-cache chatbot

# Restart
docker-compose up -d chatbot
```

### **Clean Up**

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Full cleanup (WARNING: removes all data)
docker-compose down -v
```

---

## 🐛 Troubleshooting

### **Container Won't Start**

```bash
# Check logs
docker-compose logs chatbot

# Check if port is in use
netstat -ano | findstr :8000

# Remove and recreate
docker-compose down
docker-compose up -d
```

### **Database Connection Failed**

```bash
# Check if PostgreSQL is ready
docker-compose exec postgres pg_isready -U postgres

# Check connection from app
docker-compose exec chatbot python -c "
import asyncpg
import asyncio
async def test():
    conn = await asyncpg.connect('postgresql://postgres:password@postgres:5432/chatbot')
    print(await conn.fetchval('SELECT 1'))
    await conn.close()
asyncio.run(test())
"
```

### **Out of Memory**

```bash
# Check memory usage
docker stats

# Increase limits in docker-compose.yml
services:
  postgres:
    mem_limit: 8g  # Increase limit
```

### **Slow Performance**

```bash
# Check database performance
docker-compose exec postgres psql -U postgres -d chatbot -c "
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# Vacuum and analyze
docker-compose exec postgres psql -U postgres -d chatbot -c "VACUUM ANALYZE;"
```

---

## 📊 Scaling

### **Horizontal Scaling (Multiple App Instances)**

```bash
# Scale chatbot service to 3 instances
docker-compose up -d --scale chatbot=3

# Use load balancer (nginx) to distribute traffic
```

### **Vertical Scaling (More Resources)**

Edit `docker-compose.yml`:
```yaml
services:
  postgres:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

---

## 🎯 Next Steps

After successful deployment:

1. ✅ Monitor health endpoints
2. 📊 Set up alerting (e.g., Prometheus + Grafana)
3. 🔄 Configure automated backups
4. 🧪 Run integration tests
5. 📈 Monitor performance metrics
6. 🔐 Harden security settings
7. 🚀 Deploy to production

---

## 🆘 Support

**Need help?**
- Check logs: `docker-compose logs -f`
- Test health: `curl http://localhost:8000/api/health/postgres`
- Verify database: `docker-compose exec postgres psql -U postgres -d chatbot`

**Common Issues:**
- Port already in use: Change ports in `.env`
- Out of memory: Increase Docker Desktop memory limit
- Connection refused: Check if services are healthy: `docker-compose ps`
