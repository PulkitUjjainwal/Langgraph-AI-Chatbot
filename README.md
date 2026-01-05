# MI Chat Bot - AI-Powered Trade Intelligence Chatbot

A production-ready FastAPI chatbot powered by LangGraph, Ollama LLM, and Redis for intelligent trade data queries. Features RAG (Retrieval Augmented Generation), dynamic content fetching, conversation memory, and multi-site deployment support.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Multi-Site Deployment](#multi-site-deployment)
- [Development](#development)
- [Testing](#testing)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Features

### Core Capabilities
- **RAG System**: FAISS-based vector search with Ollama embeddings (10-20x faster than OpenAI API)
- **LangGraph Workflow**: State machine-based conversation flow with tool calling
- **Redis Memory**: Distributed conversation history and dynamic content caching
- **Dynamic Content**: Fetches and embeds company-specific data from APIs
- **Hybrid Retrieval**: Combines static knowledge base with dynamic API data
- **Multi-Site Support**: Single codebase serving multiple brands (Export Genius, Market Inside)

### AI Enhancements
- **Hostility Detection**: Rule-based profanity filtering (2-8ms, no LLM overhead)
- **Progressive Questioning**: Context-aware follow-up questions
- **Industry Detection**: Automatically identifies and tailors responses to specific industries
- **Response Quality Scoring**: Ensures conversational, engaging responses
- **Smart Context Injection**: Dynamic temperature and response length based on query type

### Performance
- **In-Memory Checkpointing**: 15-20x faster than Redis checkpointing
- **Lazy Ollama Client**: No blocking on startup
- **Embedding Cache**: Reduces redundant API calls
- **Async API Calls**: Non-blocking dynamic content fetching
- **Greeting Shortcuts**: 100x faster responses for simple greetings

### API Features
- **Session Management**: Thread-based conversation persistence
- **Streaming Support**: Ready for Server-Sent Events (SSE) implementation
- **Health Checks**: Monitor Ollama, Redis, and KB status
- **CORS Enabled**: Ready for web frontend integration
- **OpenAPI Docs**: Auto-generated interactive documentation

## Architecture

```
┌─────────────────┐
│   FastAPI App   │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Manager │
    └────┬────┘
         │
    ┌────┴─────────────────────────┐
    │    LangGraph Workflow        │
    │  ┌────────────────────────┐  │
    │  │  1. Retrieval Node     │  │  (KB Search)
    │  └──────────┬─────────────┘  │
    │             │                 │
    │  ┌──────────▼─────────────┐  │
    │  │  2. Guardrail Node     │  │  (Hostility Check)
    │  └──────────┬─────────────┘  │
    │             │                 │
    │  ┌──────────▼─────────────┐  │
    │  │  3. Chatbot Node       │  │  (LLM Response)
    │  └──────────┬─────────────┘  │
    │             │                 │
    │  ┌──────────▼─────────────┐  │
    │  │  4. Tool Node          │  │  (Optional)
    │  └────────────────────────┘  │
    └─────────────────────────────┘
         │              │
    ┌────▼────┐    ┌───▼───┐
    │  Redis  │    │ Ollama│
    │ Memory  │    │  LLM  │
    └─────────┘    └───────┘
```

### Data Flow
1. **User Query** → FastAPI receives chat request
2. **Session Check** → Redis retrieves/creates session
3. **Dynamic Content** → Fetch API data if URL provided (cached in Redis)
4. **KB Retrieval** → FAISS searches static knowledge base
5. **Hybrid Merge** → Combines KB + dynamic content
6. **Guardrail** → Checks for hostility/profanity
7. **LLM Generation** → Ollama DeepSeek generates response
8. **Tool Calling** → Optional tool execution for complex queries
9. **Response** → Return to user with metadata

## Prerequisites

### Required Software
- **Python 3.10+** (tested on Python 3.10 and 3.11)
- **Redis Server** (for distributed memory and caching)
- **Ollama** (for local LLM and embeddings)

### Optional Services
- **Docker** (for containerized deployment)
- **Nginx** (for reverse proxy in production)
- **systemd** (for process management on Linux)

## Quick Start

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd "C:\MI Ticket\MI Chat Bot\Scrapper Function"
```

### 2. Install Redis

**Windows:**
```bash
# Download Redis for Windows from:
# https://github.com/microsoftarchive/redis/releases
# Or use Windows Subsystem for Linux (WSL)

# Start Redis
redis-server
```

**Linux:**
```bash
# Install Redis
sudo apt-get update
sudo apt-get install redis-server

# Start Redis
sudo systemctl start redis
sudo systemctl enable redis

# Verify Redis is running
redis-cli ping  # Should return "PONG"
```

**macOS:**
```bash
# Install via Homebrew
brew install redis

# Start Redis
brew services start redis
```

### 3. Install Ollama

**Windows/Linux/macOS:**
```bash
# Visit: https://ollama.ai/download
# Or use install script (Linux/macOS):
curl https://ollama.ai/install.sh | sh
```

### 4. Pull Required Models
```bash
# Pull embedding model (for RAG)
ollama pull nomic-embed-text

# Pull LLM model (for chat)
ollama pull deepseek-v3.1:671b-cloud
```

### 5. Create Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

### 6. Install Dependencies
```bash
# Upgrade pip
python -m pip install --upgrade pip setuptools wheel

# Install all requirements
pip install -r requirements.txt
```

### 7. Configure Environment Variables
```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your configuration
# For basic setup, default values work out of the box
```

Example `.env` file:
```env
# Site Configuration (for multi-site deployments)
SITE_ID=exportgenius
SITE_NAME=Export Genius

# Data Files
KB_CHUNKS_FILE=data/kb_exportgenius_chunks.json
FAISS_INDEX_FILE=data/faiss_exportgenius_normalized.index

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
LLM_MODEL=deepseek-v3.1:671b-cloud

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_TTL_DAYS=7

# Optional: Ollama Cloud API (if using cloud instead of local)
# OLLAMA_API_KEY=your_api_key_here
```

### 8. Verify Knowledge Base Files Exist
```bash
# Check if required data files exist
ls data/
# Should see:
# - kb_exportgenius_chunks.json (or kb_marketinside_chunks.json)
# - faiss_exportgenius_normalized.index (or faiss_marketinside_normalized.index)
```

### 9. Start the Application
```bash
# Start with uvicorn (development)
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --reload

# Or use the batch file (Windows - Market Inside)
START_MARKETINSIDE.bat
```

### 10. Test the API
Open your browser and navigate to:
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/api/health

Or use curl:
```bash
# Health check
curl http://localhost:8000/api/health

# Chat request
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What countries does Export Genius cover?",
    "session_id": "test_user_123"
  }'
```

## Project Structure

```
C:\MI Ticket\MI Chat Bot\Scrapper Function\
│
├── fastapi_chatbot.py          # Main FastAPI application
├── requirements.txt            # Python dependencies
├── requirements-minimal.txt    # Minimal dependencies for basic setup
├── .env.example                # Example environment configuration
├── START_MARKETINSIDE.bat      # Windows batch file to start Market Inside site
│
├── data/                       # Data files
│   ├── kb_exportgenius_chunks.json              # Export Genius knowledge base chunks
│   ├── faiss_exportgenius_normalized.index      # Export Genius FAISS index
│   ├── kb_marketinside_chunks.json              # Market Inside knowledge base chunks
│   ├── faiss_marketinside_normalized.index      # Market Inside FAISS index
│   └── api_data_*.json                          # Cached API responses
│
├── chatbot/                    # Modular chatbot components
│   ├── __init__.py
│   ├── models/                 # Pydantic models
│   │   ├── __init__.py
│   │   ├── api_models.py       # API request/response models
│   │   ├── requests.py
│   │   ├── responses.py
│   │   └── state.py            # LangGraph state definition
│   │
│   ├── services/               # Core services
│   │   ├── agent/              # LangGraph agent logic
│   │   │   ├── __init__.py
│   │   │   ├── chatbot_agent.py
│   │   │   └── prompts.py      # System prompts and prompt building
│   │   │
│   │   ├── llm/                # LLM clients
│   │   │   ├── __init__.py
│   │   │   └── ollama_client.py
│   │   │
│   │   └── retrieval/          # RAG components
│   │       ├── __init__.py
│   │       ├── kb_retriever.py      # Static KB retrieval
│   │       ├── hybrid_retriever.py  # KB + dynamic content
│   │       └── dynamic_content.py   # API data fetching
│   │
│   ├── integrations/           # External integrations
│   │   ├── apis/               # API clients
│   │   │   ├── __init__.py
│   │   │   ├── export_genius.py
│   │   │   ├── marketinside.py
│   │   │   ├── unified_api_client.py
│   │   │   ├── unified_client.py
│   │   │   ├── unified_formatter.py
│   │   │   └── unified_integration.py
│   │   │
│   │   ├── redis/              # Redis integration
│   │   │   ├── __init__.py
│   │   │   └── client.py
│   │   │
│   │   └── web_scraper.py      # Web scraping utilities
│   │
│   ├── security/               # Security features
│   │   ├── __init__.py
│   │   └── hostility_detector.py
│   │
│   ├── utils/                  # Utility functions
│   │   ├── __init__.py
│   │   ├── context_helpers.py
│   │   ├── exceptions.py
│   │   ├── monitoring.py       # Performance monitoring
│   │   └── query_helpers.py
│   │
│   ├── config/                 # Configuration
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   └── logging_config.py
│   │
│   ├── api/                    # API routes (future modular structure)
│   │   └── routes/
│   │
│   └── core/                   # Core helpers
│       ├── __init__.py
│       └── helpers.py
│
├── scripts/                    # Utility scripts
│   └── (migration, setup, etc.)
│
├── tests/                      # Test files
│   └── (test files)
│
├── redis_memory.py             # Redis memory manager (legacy, being migrated)
├── hostility_detector.py       # Hostility detector (legacy, being migrated)
├── export_genius_api.py        # Export Genius API client (legacy)
├── web_scraper.py              # Web scraper (legacy)
├── openai_embeddings.py        # OpenAI embeddings (deprecated - using Ollama)
│
└── venv/                       # Virtual environment (not in git)
```

## Configuration

### Environment Variables

All configuration is done via environment variables (`.env` file):

#### Site Configuration
```env
SITE_ID=exportgenius              # Site identifier (exportgenius, marketinside)
SITE_NAME=Export Genius           # Site display name
```

#### Data Files
```env
KB_CHUNKS_FILE=data/kb_exportgenius_chunks.json
FAISS_INDEX_FILE=data/faiss_exportgenius_normalized.index
```

#### Ollama Configuration
```env
OLLAMA_BASE_URL=http://localhost:11434     # Ollama server URL
OLLAMA_API_KEY=                             # Optional: Cloud API key
EMBEDDING_MODEL=nomic-embed-text            # Embedding model for RAG
LLM_MODEL=deepseek-v3.1:671b-cloud         # Chat LLM model
```

#### Redis Configuration
```env
REDIS_HOST=localhost              # Redis server host
REDIS_PORT=6379                   # Redis server port
REDIS_DB=0                        # Redis database number
REDIS_PASSWORD=                   # Optional: Redis password
REDIS_TTL_DAYS=7                  # TTL for cached data (days)
```

#### Performance Tuning
```env
DISABLE_CHECKPOINTING=false       # Set to "true" for 10-15s faster responses (no history)
```

### Multi-Site Configuration

To run multiple sites on the same machine:

**Export Genius (Port 8000):**
```env
SITE_ID=exportgenius
SITE_NAME=Export Genius
KB_CHUNKS_FILE=data/kb_exportgenius_chunks.json
FAISS_INDEX_FILE=data/faiss_exportgenius_normalized.index
REDIS_DB=0
```

**Market Inside (Port 8003):**
```env
SITE_ID=marketinside
SITE_NAME=Market Inside Data
KB_CHUNKS_FILE=data/kb_marketinside_chunks.json
FAISS_INDEX_FILE=data/faiss_marketinside_normalized.index
REDIS_DB=2
```

Run each site with:
```bash
# Export Genius
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --reload

# Market Inside
START_MARKETINSIDE.bat  # Or manually set env vars and run on port 8003
```

## API Endpoints

### Base URL
```
http://localhost:8000
```

### Endpoints

#### 1. Chat - Send a message
```http
POST /api/chat
Content-Type: application/json

{
  "message": "What countries does Export Genius cover?",
  "session_id": "user_123",
  "dynamic_url": "https://api.example.com/data/company123"  // Optional
}
```

**Response:**
```json
{
  "response": "Export Genius covers 190+ countries with comprehensive trade data...",
  "session_id": "user_123",
  "processing_time": 2.5,
  "sources_used": ["Knowledge Base", "Dynamic Content (Redis)"]
}
```

#### 2. Initialize Session - Pre-cache content and generate questions
```http
POST /api/init
Content-Type: application/json

{
  "session_id": "user_123",
  "dynamic_url": "https://api.example.com/data/company123"  // Optional
}
```

**Response:**
```json
{
  "status": "success",
  "suggested_questions": [
    "What countries does Export Genius cover?",
    "How can Export Genius help my business?",
    "What data types are available?",
    "How do I access the API?",
    "What makes Export Genius unique?"
  ],
  "cache_status": {
    "cache_hit": false,
    "cached_at": "2024-01-15T10:30:00"
  },
  "processing_time": 3.2,
  "dynamic_url_processed": true
}
```

#### 3. Reset Session
```http
POST /api/reset
Content-Type: application/json

{
  "session_id": "user_123"
}
```

#### 4. Get Conversation History
```http
GET /api/history/{session_id}?limit=10
```

#### 5. Health Check
```http
GET /api/health
```

**Response:**
```json
{
  "status": "healthy",
  "ollama_status": "not_checked",
  "kb_loaded": true,
  "active_sessions": 5,
  "uptime_seconds": 3600
}
```

#### 6. Redis Statistics
```http
GET /api/redis/stats
```

**Response:**
```json
{
  "redis_stats": {
    "conversations": 10,
    "embeddings": 5,
    "sessions": 8,
    "memory_used_mb": 25.5,
    "memory_peak_mb": 30.2
  },
  "status": "healthy"
}
```

### Interactive API Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Multi-Site Deployment

This chatbot supports running multiple brand sites from a single codebase.

### Configuration Strategy
Each site has:
- **Unique SITE_ID**: Identifies the site (e.g., `exportgenius`, `marketinside`)
- **Unique Redis DB**: Separate conversation storage (e.g., DB 0, DB 2)
- **Unique Knowledge Base**: Site-specific FAISS index and chunks
- **Unique Port**: Different ports for each site (e.g., 8000, 8003)

### Example: Running Two Sites

**Site 1: Export Genius (Port 8000)**
```bash
# Set environment variables
export SITE_ID=exportgenius
export SITE_NAME="Export Genius"
export REDIS_DB=0
export KB_CHUNKS_FILE=data/kb_exportgenius_chunks.json
export FAISS_INDEX_FILE=data/faiss_exportgenius_normalized.index

# Start server
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000
```

**Site 2: Market Inside (Port 8003)**
```bash
# Use batch file (Windows)
START_MARKETINSIDE.bat

# Or manually (Linux/macOS)
export SITE_ID=marketinside
export SITE_NAME="Market Inside Data"
export REDIS_DB=2
export KB_CHUNKS_FILE=data/kb_marketinside_chunks.json
export FAISS_INDEX_FILE=data/faiss_marketinside_normalized.index

python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8003
```

Both sites run independently with isolated data and conversations.

## Development

### Running in Development Mode
```bash
# Activate virtual environment
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/macOS

# Start with auto-reload
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --reload
```

### Code Structure Guidelines
- **Modular Design**: Keep components in `chatbot/` package
- **Type Hints**: Use Python type hints for all functions
- **Async/Await**: Use async for I/O operations (Redis, API calls)
- **Error Handling**: Use try-except blocks with detailed logging
- **Environment Variables**: Use `.env` for configuration (never hardcode)

### Adding a New API Integration
1. Create client in `chatbot/integrations/apis/your_api.py`
2. Add to `unified_api_client.py`
3. Update `dynamic_content.py` to support new API
4. Add environment variables to `.env.example`
5. Update documentation

## Testing

### Manual Testing
```bash
# Test health endpoint
curl http://localhost:8000/api/health

# Test chat endpoint
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello",
    "session_id": "test_123"
  }'

# Test init endpoint
curl -X POST http://localhost:8000/api/init \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_123"
  }'
```

### Automated Testing
```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests (when test files are added)
pytest tests/ -v
```

### Performance Testing
Monitor performance metrics:
- Retrieval time: < 1s
- Generation time: < 30s
- Total response time: < 35s

Enable performance logging:
```python
Config.ENABLE_PERFORMANCE_LOGGING = True
```

## Production Deployment

### Linux Server Setup

#### 1. Install System Dependencies
```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python 3.10+
sudo apt-get install python3.10 python3.10-venv python3-pip -y

# Install Redis
sudo apt-get install redis-server -y
sudo systemctl start redis
sudo systemctl enable redis

# Install Ollama
curl https://ollama.ai/install.sh | sh
```

#### 2. Pull Models
```bash
ollama pull nomic-embed-text
ollama pull deepseek-v3.1:671b-cloud
```

#### 3. Create Service User
```bash
sudo useradd -m -s /bin/bash chatbot
sudo su - chatbot
```

#### 4. Deploy Application
```bash
# Clone repository
git clone <your-repo> /home/chatbot/app
cd /home/chatbot/app

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Edit configuration
```

#### 5. Create systemd Service
```bash
sudo nano /etc/systemd/system/chatbot.service
```

Add:
```ini
[Unit]
Description=MI Chat Bot API
After=network.target redis.service

[Service]
Type=simple
User=chatbot
WorkingDirectory=/home/chatbot/app
Environment="PATH=/home/chatbot/app/venv/bin"
ExecStart=/home/chatbot/app/venv/bin/uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable chatbot
sudo systemctl start chatbot
sudo systemctl status chatbot
```

#### 6. Configure Nginx (Reverse Proxy)
```bash
sudo nano /etc/nginx/sites-available/chatbot
```

Add:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for future streaming)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

Enable and restart:
```bash
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### 7. SSL with Let's Encrypt
```bash
sudo apt-get install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

### Docker Deployment (Alternative)

```dockerfile
# Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    redis-server \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl https://ollama.ai/install.sh | sh

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Start services
CMD service redis-server start && \
    ollama serve & \
    sleep 5 && \
    ollama pull nomic-embed-text && \
    ollama pull deepseek-v3.1:671b-cloud && \
    uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000
```

Build and run:
```bash
docker build -t mi-chatbot .
docker run -d -p 8000:8000 --name chatbot mi-chatbot
```

## Troubleshooting

### Common Issues

#### 1. Redis Connection Error
```
Error: Could not connect to Redis at localhost:6379
```

**Solution:**
```bash
# Check if Redis is running
redis-cli ping

# Start Redis
# Windows: redis-server
# Linux: sudo systemctl start redis
```

#### 2. Ollama Not Found
```
Error: Could not connect to Ollama
```

**Solution:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/version

# Start Ollama
ollama serve
```

#### 3. Model Not Found
```
Error: model 'nomic-embed-text' not found
```

**Solution:**
```bash
# Pull required models
ollama pull nomic-embed-text
ollama pull deepseek-v3.1:671b-cloud
```

#### 4. FAISS Index Not Found
```
FileNotFoundError: FAISS index not found
```

**Solution:**
- Verify `FAISS_INDEX_FILE` path in `.env`
- Ensure data files exist in `data/` directory
- Check file permissions

#### 5. Port Already in Use
```
Error: [Errno 98] Address already in use
```

**Solution:**
```bash
# Find process using port
netstat -ano | findstr :8000  # Windows
lsof -i :8000  # Linux/macOS

# Kill process or use different port
python -m uvicorn fastapi_chatbot:app --port 8001
```

#### 6. Slow Response Times
If responses take > 40s:

**Check:**
1. Redis latency: `redis-cli --latency`
2. Ollama response time: Check Ollama logs
3. Network connection to cloud API (if using OLLAMA_API_KEY)

**Solutions:**
- Use local Ollama instead of cloud API
- Disable checkpointing: `DISABLE_CHECKPOINTING=true`
- Increase Redis memory
- Use faster hardware for Ollama

### Debugging Tips

#### Enable Debug Logging
The application has extensive debug logging built-in. Check console output for:
- `[DEBUG]` - Debug information
- `[CHAT START]` - New conversation start
- `[FIND]` - Retrieval operations
- `[AI]` - LLM calls
- `[ERROR]` - Error messages

#### Check Redis Keys
```bash
# Connect to Redis
redis-cli

# List all keys
KEYS *

# Check specific session
GET conversation:user_123

# Check embeddings cache
GET embeddings:https://example.com
```

#### Monitor Performance
```bash
# Watch logs in real-time
tail -f /var/log/chatbot/app.log  # If logging to file

# Check Redis stats
redis-cli INFO stats

# Check Ollama status
ollama list
```

## Performance Metrics

Expected performance on modern hardware:

- **Greeting Response**: < 0.1s (instant, no LLM call)
- **Simple Query**: 2-5s
- **Standard Query**: 5-15s
- **Complex Query with Dynamic Content**: 15-35s
- **First Message (Cold Start)**: +5s (model loading)

Optimizations:
- Embedding cache reduces retrieval by 50%
- In-memory checkpointing: 15-20x faster than Redis checkpointing
- Lazy Ollama client: No startup delay
- Async API calls: Non-blocking dynamic content fetch

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is proprietary software. All rights reserved.

## Support

For issues, questions, or feature requests:
- Create an issue in the GitHub repository
- Contact the development team

---

**Note**: This README assumes you have access to the required data files (FAISS index and knowledge base chunks). If you're setting up a new deployment, you'll need to generate these files using the knowledge base building scripts.
