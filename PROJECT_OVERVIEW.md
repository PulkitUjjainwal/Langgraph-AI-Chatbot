# MI Chat Bot - Project Overview

## What is This?

MI Chat Bot is an enterprise-grade AI chatbot system designed for trade intelligence platforms. It uses state-of-the-art LLM technology (DeepSeek via Ollama) combined with RAG (Retrieval Augmented Generation) to answer questions about international trade data, companies, and market intelligence.

## Key Features

### 1. Multi-Site Architecture
- **Single Codebase, Multiple Brands**: Same application powers Export Genius and Market Inside Data
- **Isolated Data**: Each site has its own knowledge base, Redis database, and configuration
- **Easy Scaling**: Add new sites by creating new knowledge bases and config files

### 2. Intelligent Conversation
- **Context-Aware**: Remembers conversation history using Redis
- **RAG-Powered**: Retrieves relevant information from knowledge base before answering
- **Dynamic Content**: Can fetch and embed real-time company data from APIs
- **Hostility Detection**: Filters profanity and hostile messages
- **Progressive Questioning**: Asks smart follow-up questions to understand user needs

### 3. High Performance
- **Local Embeddings**: Uses Ollama embeddings (10-20x faster than OpenAI API)
- **Redis Caching**: Stores conversation history and dynamic content embeddings
- **In-Memory Checkpointing**: 15-20x faster than Redis-based checkpointing
- **Async Operations**: Non-blocking API calls and database operations
- **Greeting Shortcuts**: Instant responses for simple greetings (100x faster)

### 4. Production-Ready
- **FastAPI**: Modern async Python web framework
- **Systemd Integration**: Linux service management
- **Nginx Support**: Reverse proxy with SSL
- **Docker Compatible**: Containerization support
- **Health Monitoring**: Built-in health checks and performance metrics

## Technology Stack

### Core Technologies
- **Python 3.10+**: Programming language
- **FastAPI**: Web framework for REST API
- **LangGraph**: State machine for conversation flow
- **Ollama**: Local LLM server (DeepSeek v3.1)
- **Redis**: Conversation memory and caching
- **FAISS**: Vector similarity search
- **BeautifulSoup**: Web scraping (optional)

### Key Libraries
- `langchain-core`: LLM abstractions
- `langchain-ollama`: Ollama integration
- `langgraph`: Workflow orchestration
- `faiss-cpu`: Vector search
- `redis`: Redis client
- `fastapi`: Web framework
- `uvicorn`: ASGI server
- `pydantic`: Data validation

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI Application                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ /api/chat    │  │ /api/init    │  │ /api/health  │  │
│  │ (Main Chat)  │  │ (Pre-cache)  │  │ (Monitoring) │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │    ChatbotManager             │
         │  - Session management         │
         │  - Dynamic content fetching   │
         │  - Question generation        │
         └───────────┬───────────────────┘
                     │
                     ▼
         ┌───────────────────────────────┐
         │    LangGraph Workflow         │
         │  ┌─────────────────────────┐  │
         │  │ 1. Retrieval Node       │  │ (FAISS search)
         │  │    ↓                    │  │
         │  │ 2. Guardrail Node       │  │ (Hostility check)
         │  │    ↓                    │  │
         │  │ 3. Chatbot Node         │  │ (LLM generation)
         │  │    ↓                    │  │
         │  │ 4. Tool Node (optional) │  │ (Tool calling)
         │  └─────────────────────────┘  │
         └───────┬───────────┬───────────┘
                 │           │
        ┌────────▼─────┐  ┌─▼──────────┐
        │ Redis        │  │ Ollama     │
        │ - Sessions   │  │ - LLM      │
        │ - Embeddings │  │ - Embed    │
        │ - History    │  │            │
        └──────────────┘  └────────────┘
```

## Data Flow

### 1. User Sends Message
```
POST /api/chat
{
  "message": "What countries does Export Genius cover?",
  "session_id": "user_123",
  "dynamic_url": "https://api.example.com/company/123"  // Optional
}
```

### 2. Dynamic Content Fetching (if URL provided)
- Check Redis cache for embeddings
- If cache miss: Fetch from API
- Chunk content into 500-char segments
- Generate embeddings using Ollama
- Store in Redis for future use

### 3. Knowledge Base Retrieval
- Convert user query to embedding
- Search FAISS index for similar chunks
- Return top 5 most relevant chunks

### 4. Hybrid Context Building
- Merge dynamic content (if available) with KB chunks
- Prioritize dynamic content (company-specific data)
- Add conversation history

### 5. Guardrail Check
- Check for profanity/hostility (2-8ms)
- Detect intent (clean, question, abuse, dismissal)
- Pass through or return canned response

### 6. LLM Generation
- Build system prompt with merged context
- Adjust temperature based on query type
- Send to Ollama DeepSeek model
- Post-process response (remove markdown, etc.)

### 7. Response
```json
{
  "response": "Export Genius covers 190+ countries...",
  "session_id": "user_123",
  "processing_time": 3.2,
  "sources_used": ["Knowledge Base", "Dynamic Content"]
}
```

## File Organization

### Main Application
- `fastapi_chatbot.py`: Main FastAPI application
- `requirements.txt`: Python dependencies
- `.env`: Environment configuration (not in git)
- `.env.example`: Example configuration

### Modular Components (`chatbot/`)
- `models/`: Pydantic data models
- `services/`: Core services (retrieval, LLM, agent)
- `integrations/`: External APIs and Redis
- `security/`: Hostility detection
- `utils/`: Helper functions
- `config/`: Configuration management

### Data Files (`data/`)
- `kb_<site>_chunks.json`: Knowledge base text chunks
- `faiss_<site>_normalized.index`: FAISS vector index
- `api_data_*.json`: Cached API responses
- `conversation_history/`: Chat histories (Redis backup)

### Scripts
- `START_MARKETINSIDE.bat`: Windows batch file for Market Inside
- `scripts/`: Utility scripts

## Configuration

### Multi-Site Setup
Each site needs:
1. **Site ID**: Unique identifier (`exportgenius`, `marketinside`)
2. **Knowledge Base**: FAISS index and chunks JSON
3. **Redis DB**: Separate Redis database number (0, 2, etc.)
4. **Port**: Unique port number (8000, 8003, etc.)

### Environment Variables
```env
# Site Configuration
SITE_ID=exportgenius
SITE_NAME=Export Genius
KB_CHUNKS_FILE=data/kb_exportgenius_chunks.json
FAISS_INDEX_FILE=data/faiss_exportgenius_normalized.index

# Redis (separate DB per site)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=deepseek-v3.1:671b-cloud
EMBEDDING_MODEL=nomic-embed-text
```

## API Endpoints

### Chat
```http
POST /api/chat
```
Send a message and get response with conversation history.

### Initialize
```http
POST /api/init
```
Pre-cache dynamic content and generate suggested questions.

### Reset
```http
POST /api/reset
```
Clear conversation history for a session.

### Health
```http
GET /api/health
```
Check system health (Redis, Ollama, KB loaded).

### Redis Stats
```http
GET /api/redis/stats
```
Get Redis cache statistics.

## Performance Metrics

### Expected Response Times
- **Greeting**: < 0.1s (instant)
- **Simple Query**: 2-5s
- **Standard Query**: 5-15s
- **Complex with Dynamic Content**: 15-35s

### Bottlenecks
1. **LLM Generation**: 20-30s (cloud API network latency)
2. **Dynamic Content Fetch**: 3-5s (first time, cached after)
3. **FAISS Search**: < 0.5s (fast)
4. **Redis Operations**: < 0.1s (local)

### Optimizations
- Embedding cache: 50% faster on repeated queries
- Greeting shortcuts: 100x faster
- In-memory checkpointing: 15-20x faster than Redis
- Local Ollama embeddings: 10-20x faster than OpenAI API

## Security Features

### 1. Hostility Detection
- Rule-based profanity filtering
- Intent classification (clean, question, abuse, dismissal)
- Graceful handling without blocking users
- 2-8ms overhead (no LLM call)

### 2. API Token Authentication
- Bearer token for Export Genius API
- Bearer token for Market Inside API
- Stored in environment variables (not in code)

### 3. Rate Limiting
- Can be configured in Nginx
- Prevents abuse and DDoS

### 4. CORS
- Configured for web frontend integration
- Allows specific origins only

## Deployment Strategies

### Development
```bash
python -m uvicorn fastapi_chatbot:app --reload --port 8000
```

### Production (systemd)
```bash
sudo systemctl start chatbot
sudo systemctl enable chatbot  # Auto-start on boot
```

### Production (Docker)
```bash
docker build -t mi-chatbot .
docker run -d -p 8000:8000 mi-chatbot
```

### Multi-Site Production
```bash
# Export Genius (Port 8000)
sudo systemctl start chatbot-exportgenius

# Market Inside (Port 8003)
sudo systemctl start chatbot-marketinside
```

## Monitoring

### Health Checks
```bash
curl http://localhost:8000/api/health
```

### Logs
```bash
# Application logs
sudo journalctl -u chatbot -f

# Nginx logs
sudo tail -f /var/log/nginx/chatbot_access.log
sudo tail -f /var/log/nginx/chatbot_error.log

# Redis logs
redis-cli MONITOR
```

### Performance Metrics
- Built-in performance logging
- Response time tracking
- Source usage statistics
- Session count monitoring

## Backup and Recovery

### What to Backup
1. **Data Files**: FAISS index, chunks JSON
2. **Configuration**: `.env` file
3. **Redis Database**: `dump.rdb`
4. **Conversation History**: Redis exports

### Backup Script
```bash
./backup.sh  # Creates timestamped backups
```

### Restore Process
1. Stop services
2. Restore data files
3. Restore Redis database
4. Restart services

## Troubleshooting

### Common Issues

#### 1. Redis Connection Error
```bash
redis-cli ping  # Check if Redis is running
sudo systemctl start redis  # Start Redis
```

#### 2. Ollama Not Found
```bash
ollama serve  # Start Ollama
ollama pull nomic-embed-text  # Pull embedding model
ollama pull deepseek-v3.1:671b-cloud  # Pull LLM
```

#### 3. FAISS Index Not Found
- Check `FAISS_INDEX_FILE` path in `.env`
- Verify file exists in `data/` directory

#### 4. Slow Responses
- Check Redis latency: `redis-cli --latency`
- Check Ollama response time
- Use local Ollama instead of cloud API
- Disable checkpointing: `DISABLE_CHECKPOINTING=true`

## Development Workflow

### Adding a New Feature
1. Create branch: `git checkout -b feature/new-feature`
2. Implement in modular structure (`chatbot/`)
3. Update tests
4. Test locally
5. Update documentation
6. Create pull request

### Adding a New Site
1. Generate knowledge base (FAISS index + chunks)
2. Create `.env` with new site config
3. Create systemd service file
4. Start service on unique port
5. Configure Nginx virtual host

## Future Enhancements

### Planned Features
- [ ] Streaming responses (SSE)
- [ ] Multi-language support
- [ ] Voice input/output
- [ ] Chat history export
- [ ] Advanced analytics dashboard
- [ ] A/B testing framework
- [ ] Sentiment analysis
- [ ] Custom knowledge base builder UI

### Performance Improvements
- [ ] Quantized models for faster inference
- [ ] GPU acceleration for embeddings
- [ ] Distributed Redis cluster
- [ ] CDN for static assets
- [ ] Response caching layer

## Contributing

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for development setup.

## Documentation

- **README.md**: Complete documentation
- **SETUP_GUIDE.md**: Quick setup instructions
- **DEPLOYMENT.md**: Production deployment guide
- **PROJECT_OVERVIEW.md**: This file (high-level overview)

## License

Proprietary software. All rights reserved.

## Support

For issues or questions:
- Create an issue in the repository
- Contact the development team
- Check documentation and troubleshooting guides

---

**Last Updated**: 2026-01-05
**Version**: 1.0.0
**Maintainers**: Development Team
