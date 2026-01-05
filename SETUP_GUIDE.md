# Quick Setup Guide

This guide will help you get the MI Chat Bot running on a new device in under 10 minutes.

## Prerequisites Checklist

Before you begin, ensure you have:
- [ ] Python 3.10 or higher installed
- [ ] Git installed (to clone the repository)
- [ ] 8GB+ RAM available
- [ ] 10GB+ disk space available

## Step-by-Step Setup

### 1. Install Redis (5 minutes)

#### Windows
```bash
# Option 1: Use WSL (Windows Subsystem for Linux)
wsl --install
wsl
sudo apt-get update && sudo apt-get install redis-server -y
sudo service redis-server start

# Option 2: Download Redis for Windows
# Visit: https://github.com/microsoftarchive/redis/releases
# Download and install the latest .msi file
# Redis will start automatically as a Windows service
```

#### Linux
```bash
sudo apt-get update
sudo apt-get install redis-server -y
sudo systemctl start redis
sudo systemctl enable redis
redis-cli ping  # Should return "PONG"
```

#### macOS
```bash
brew install redis
brew services start redis
redis-cli ping  # Should return "PONG"
```

### 2. Install Ollama (3 minutes)

#### All Platforms
Visit [https://ollama.ai/download](https://ollama.ai/download) and download the installer for your OS.

Or use the install script (Linux/macOS):
```bash
curl https://ollama.ai/install.sh | sh
```

#### Pull Required Models
```bash
# This will download ~4GB of models
ollama pull nomic-embed-text     # Embedding model (~1GB)
ollama pull deepseek-v3.1:671b-cloud  # LLM model (~3GB)
```

### 3. Set Up Python Environment (2 minutes)

```bash
# Navigate to project directory
cd "C:\MI Ticket\MI Chat Bot\Scrapper Function"

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Upgrade pip
python -m pip install --upgrade pip setuptools wheel

# Install all dependencies
pip install -r requirements.txt
```

### 4. Configure Environment Variables (1 minute)

```bash
# Copy example environment file
cp .env.example .env

# For basic local setup, the defaults work!
# No need to edit unless you have specific requirements
```

### 5. Verify Installation (1 minute)

```bash
# Check Redis
redis-cli ping  # Should return "PONG"

# Check Ollama
curl http://localhost:11434/api/version

# Check Python environment
python --version  # Should be 3.10+

# Verify data files exist
ls data/
# Should see:
# - kb_exportgenius_chunks.json or kb_marketinside_chunks.json
# - faiss_exportgenius_normalized.index or faiss_marketinside_normalized.index
```

### 6. Start the Application (30 seconds)

```bash
# Ensure virtual environment is activated
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate

# Start the FastAPI server
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --reload
```

### 7. Test the Application (30 seconds)

#### Option 1: Web Browser
Open: [http://localhost:8000/docs](http://localhost:8000/docs)

Try the `/api/health` endpoint to verify everything is working.

#### Option 2: Command Line
```bash
# Health check
curl http://localhost:8000/api/health

# Chat test
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "session_id": "test_123"}'
```

## Common Issues and Quick Fixes

### Issue 1: Redis Not Running
```bash
# Windows (WSL)
sudo service redis-server start

# Linux
sudo systemctl start redis

# macOS
brew services start redis
```

### Issue 2: Ollama Not Running
```bash
# Start Ollama server
ollama serve

# In another terminal, verify
curl http://localhost:11434/api/version
```

### Issue 3: Models Not Found
```bash
# Pull models again
ollama pull nomic-embed-text
ollama pull deepseek-v3.1:671b-cloud

# Verify models are installed
ollama list
```

### Issue 4: Port 8000 Already in Use
```bash
# Use a different port
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8001 --reload
```

### Issue 5: Virtual Environment Not Activated
```bash
# You'll see errors like "module not found"
# Solution: Activate the virtual environment

# Windows:
venv\Scripts\activate

# Linux/macOS:
source venv/bin/activate

# Verify activation (should show venv path):
which python  # Linux/macOS
where python  # Windows
```

## What's Next?

Once the application is running:

1. **Read the Full Documentation**: See [README.md](README.md) for detailed information
2. **Explore the API**: Visit http://localhost:8000/docs for interactive API documentation
3. **Test Conversations**: Try asking questions about trade data, countries, etc.
4. **Configure for Your Needs**: Edit `.env` to customize the chatbot
5. **Deploy to Production**: Follow the production deployment guide in README.md

## Need Help?

- Check the [Troubleshooting section](README.md#troubleshooting) in README.md
- Review application logs for error messages
- Ensure all prerequisites are properly installed

## Quick Reference Commands

```bash
# Start Redis
# Windows: wsl sudo service redis-server start
# Linux: sudo systemctl start redis
# macOS: brew services start redis

# Start Ollama (usually auto-starts)
ollama serve

# Activate virtual environment
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate

# Start application
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --reload

# Check health
curl http://localhost:8000/api/health

# View API docs
# Browser: http://localhost:8000/docs
```

## Multi-Site Setup

To run multiple sites (Export Genius + Market Inside):

### Site 1: Export Genius (Port 8000)
```bash
# Edit .env
SITE_ID=exportgenius
SITE_NAME=Export Genius
REDIS_DB=0
KB_CHUNKS_FILE=data/kb_exportgenius_chunks.json
FAISS_INDEX_FILE=data/faiss_exportgenius_normalized.index

# Start
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --reload
```

### Site 2: Market Inside (Port 8003)
```bash
# Use the provided batch file (Windows)
START_MARKETINSIDE.bat

# Or set environment variables manually and start
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8003 --reload
```

---

**Setup Time**: ~10 minutes total
**Difficulty**: Easy (just follow the steps!)
**Prerequisites**: Python 3.10+, Redis, Ollama

Happy chatting! 🤖
