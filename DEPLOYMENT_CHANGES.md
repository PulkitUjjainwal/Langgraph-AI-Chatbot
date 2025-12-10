# Deployment Configuration Changes

## Overview
This document outlines the changes needed to deploy the chatbot with the new hybrid Ollama setup:
- **Embeddings**: Local Ollama server (nomic-embed-text)
- **LLM**: Ollama Cloud API (deepseek-v3.1:671b-cloud)

---

## 1. Server Prerequisites

### Required Services:
1. **Local Ollama Server** (for embeddings)
   - Must be installed and running on the deployment server
   - Required model: `nomic-embed-text`

2. **Redis Server** (for session management)
   - Already configured in your setup

3. **Internet Access** (for Ollama Cloud API)
   - Server needs outbound HTTPS access to `https://ollama.com`

---

## 2. Installation Steps

### Step 1: Install Ollama on Production Server

```bash
# SSH into your production server
ssh $SERVER_USER@$SERVER_IP

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Verify installation
ollama --version

# Pull the embedding model
ollama pull nomic-embed-text

# Verify the model is available
ollama list

# Start Ollama service (if not auto-started)
sudo systemctl start ollama
sudo systemctl enable ollama

# Verify Ollama is running
curl http://localhost:11434/api/tags
```

### Step 2: Configure Environment Variables

Create/update `.env` file on the production server at `/opt/eg-chatbot/.env`:

```bash
cd /opt/eg-chatbot

# Create .env file with proper configuration
cat > .env << 'EOF'
# ============================================================================
# Export Genius Chatbot API - Production Environment
# ============================================================================

# ----------------------------------------------------------------------------
# Export Genius API Authentication
# ----------------------------------------------------------------------------
EXPORT_GENIUS_BEARER_TOKEN=your_token_here

# ----------------------------------------------------------------------------
# Redis Configuration (Session Management & Caching)
# ----------------------------------------------------------------------------
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_TTL_DAYS=1

# ----------------------------------------------------------------------------
# LLM Configuration - HYBRID SETUP
# ----------------------------------------------------------------------------
LLM_MODEL=deepseek-v3.1:671b-cloud
EMBEDDING_MODEL=nomic-embed-text

# Ollama Cloud API (for LLM only)
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_API_KEY=006b1854cb5743d5a8a6e2baf09d163c.NQNQ-X28yY6S7WD0UtAp4_pb

# Note: Embeddings will use LOCAL Ollama at http://localhost:11434
# The code automatically routes embeddings to local and LLM to cloud

# ----------------------------------------------------------------------------
# API Server Configuration
# ----------------------------------------------------------------------------
API_HOST=0.0.0.0
API_PORT=8000
EOF

# Secure the .env file
chmod 600 .env
```

### Step 3: Update Dependencies

The current `requirements.txt` is already correct with:
- `ollama==0.3.3`
- `langchain-ollama==0.2.0`

No changes needed here.

### Step 4: Update PM2 Configuration

The `ecosystem.config.js` has been updated. Key changes:
- Added `EMBEDDING_MODEL` environment variable
- Changed `OLLAMA_BASE_URL` to cloud API
- Added note about API key in .env

---

## 3. Deployment Checklist

### Pre-Deployment:
- [x] Code changes committed to Git
- [x] `ecosystem.config.js` updated with cloud API URL
- [ ] `.env` file created on server with API keys
- [ ] Ollama installed on production server
- [ ] `nomic-embed-text` model pulled locally
- [ ] Ollama service running on localhost:11434
- [ ] Redis running and accessible
- [ ] Server has outbound internet access to ollama.com

### During Deployment:
```bash
# 1. Push changes to Git
git add .
git commit -m "Update to hybrid Ollama setup (local embeddings + cloud LLM)"
git push origin main

# 2. GitHub Actions will automatically deploy
# OR manually deploy via SSH:

ssh $SERVER_USER@$SERVER_IP << 'ENDSSH'
  cd /opt/eg-chatbot

  # Pull latest code
  git pull origin main

  # Activate virtual environment
  source venv/bin/activate

  # Install/update dependencies
  pip install --upgrade pip
  pip install -r requirements.txt

  # Verify Ollama is running
  curl http://localhost:11434/api/tags

  # Reload PM2
  pm2 reload ecosystem.config.js --env production

  # Check status
  pm2 status
  pm2 logs eg-chatbot-api --lines 50
ENDSSH
```

### Post-Deployment Verification:

```bash
# 1. Check service status
ssh $SERVER_USER@$SERVER_IP
pm2 status
pm2 logs eg-chatbot-api --lines 100

# 2. Verify Ollama local is working
curl http://localhost:11434/api/embed \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"model":"nomic-embed-text","input":"test"}'

# 3. Test API health endpoint
curl http://$SERVER_IP:8000/api/health

# 4. Test embeddings (should use LOCAL)
curl -X POST http://$SERVER_IP:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "test embeddings",
    "session_id": "test_deployment"
  }'

# 5. Check logs for confirmation
# You should see:
#   - "HTTP Request: POST http://localhost:11434/api/embed" (embeddings)
#   - "HTTP Request: POST https://ollama.com/api/chat" (LLM)
pm2 logs eg-chatbot-api --lines 50
```

---

## 4. Monitoring & Troubleshooting

### Expected Log Output:
```
INFO:httpx:HTTP Request: POST http://localhost:11434/api/embed "HTTP/1.1 200 OK"
INFO:httpx:HTTP Request: POST https://ollama.com/api/chat "HTTP/1.1 200 OK"
```

### Common Issues:

#### Issue 1: "Connection refused to localhost:11434"
**Solution:**
```bash
# Check if Ollama is running
sudo systemctl status ollama

# Start Ollama if not running
sudo systemctl start ollama

# Test manually
curl http://localhost:11434/api/tags
```

#### Issue 2: "401 Unauthorized" from cloud API
**Solution:**
```bash
# Verify API key in .env file
cat /opt/eg-chatbot/.env | grep OLLAMA_API_KEY

# Test API key manually
curl -X POST https://ollama.com/api/chat \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v3.1:671b-cloud",
    "messages": [{"role": "user", "content": "test"}],
    "stream": false
  }'
```

#### Issue 3: Model not found
**Solution:**
```bash
# Pull the embedding model
ollama pull nomic-embed-text

# Verify it's available
ollama list | grep nomic
```

#### Issue 4: Slow embeddings
**Solution:**
- Local Ollama embeddings should be fast (< 100ms)
- Check server resources: `htop` or `top`
- Verify no network issues with: `ping localhost`

---

## 5. Rollback Plan

If deployment fails:

```bash
ssh $SERVER_USER@$SERVER_IP << 'ENDSSH'
  cd /opt/eg-chatbot

  # Revert to previous commit
  git log --oneline -5
  git reset --hard PREVIOUS_COMMIT_HASH

  # Reload PM2
  pm2 reload ecosystem.config.js --env production

  # Verify
  pm2 status
ENDSSH
```

---

## 6. Performance Expectations

### With Hybrid Setup:
- **Embeddings**: 50-100ms (local)
- **LLM Response**: 1-3 seconds (cloud API)
- **Total Response Time**: 1-4 seconds

### Resource Usage (per request):
- **CPU**: Moderate (embeddings use local CPU)
- **Memory**: ~200-300MB per worker
- **Network**: Only LLM calls use internet bandwidth

---

## 7. Cost Optimization

### Benefits of Hybrid Approach:
1. **Embeddings are FREE** (local server, no API calls)
2. **LLM calls only** hit the cloud API (cost reduction)
3. **Faster embeddings** (no network latency)
4. **More reliable** (embeddings work even if internet is down)

### Monitoring Costs:
- Track cloud API usage in Ollama dashboard
- Monitor number of LLM calls vs embeddings
- Embeddings should be 5-10x more frequent than LLM calls

---

## 8. Security Considerations

### API Key Management:
```bash
# Secure .env file permissions
chmod 600 /opt/eg-chatbot/.env

# Verify owner
ls -la /opt/eg-chatbot/.env

# Should show: -rw------- deploy deploy .env
```

### Firewall Rules:
```bash
# Local Ollama should NOT be exposed to internet
sudo ufw status
# Port 11434 should NOT be in allowed list

# Only expose API port (8000) via nginx reverse proxy
```

---

## 9. GitHub Secrets Configuration

Ensure these secrets are set in GitHub repository settings:
- `SSH_PRIVATE_KEY`: SSH key for deployment
- `SERVER_IP`: Production server IP
- `SERVER_USER`: SSH username (e.g., "deploy")
- `DEPLOY_PATH`: Deployment path (e.g., "/opt/eg-chatbot")

**Note:** Do NOT add `OLLAMA_API_KEY` to GitHub secrets. It should only be in the `.env` file on the server.

---

## 10. Testing Deployment

### Automated Test Script:
```bash
#!/bin/bash
# Save as test_deployment.sh

echo "Testing deployment..."

# Health check
echo "1. Health check..."
curl -f http://$SERVER_IP:8000/api/health || exit 1

# Test chat endpoint
echo "2. Testing chat endpoint..."
RESPONSE=$(curl -s -X POST http://$SERVER_IP:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is Export Genius?",
    "session_id": "deployment_test"
  }')

echo "$RESPONSE" | jq '.response' || exit 1

echo "✅ All tests passed!"
```

---

## Summary

The deployment now uses a **hybrid approach**:
- **Embeddings**: Local Ollama (free, fast, reliable)
- **LLM**: Cloud API (scalable, no local GPU needed)

This provides the best of both worlds: cost-effective embeddings with powerful cloud LLM.
