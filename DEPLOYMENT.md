# Production Deployment Guide

This guide covers deploying the MI Chat Bot to a production Linux server with systemd, nginx, and SSL.

## Table of Contents
- [Server Requirements](#server-requirements)
- [Initial Server Setup](#initial-server-setup)
- [Application Deployment](#application-deployment)
- [Systemd Service Configuration](#systemd-service-configuration)
- [Nginx Reverse Proxy](#nginx-reverse-proxy)
- [SSL/TLS with Let's Encrypt](#ssltls-with-lets-encrypt)
- [Monitoring and Logging](#monitoring-and-logging)
- [Backup and Recovery](#backup-and-recovery)
- [Scaling](#scaling)

## Server Requirements

### Minimum Specs
- **CPU**: 4 cores (8+ recommended for multiple sites)
- **RAM**: 8GB (16GB+ recommended)
- **Disk**: 50GB SSD
- **OS**: Ubuntu 22.04 LTS or later
- **Network**: 100 Mbps+

### Software Stack
- Python 3.10+
- Redis 6.0+
- Ollama (for LLM)
- Nginx 1.18+
- systemd (process management)

## Initial Server Setup

### 1. Update System
```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y build-essential git curl wget
```

### 2. Create Service User
```bash
# Create dedicated user (no shell access for security)
sudo useradd -m -s /bin/bash chatbot
sudo usermod -aG sudo chatbot  # Only if needed for specific tasks
```

### 3. Install Python 3.10+
```bash
# Check Python version
python3 --version

# If < 3.10, install from deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
sudo apt-get install -y python3.10 python3.10-venv python3.10-dev python3-pip
```

### 4. Install Redis
```bash
sudo apt-get install -y redis-server

# Configure Redis for production
sudo nano /etc/redis/redis.conf
# Recommended changes:
# - maxmemory 2gb
# - maxmemory-policy allkeys-lru
# - save 900 1
# - save 300 10

# Start and enable Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Test Redis
redis-cli ping  # Should return PONG
```

### 5. Install Ollama
```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull required models (this will take time!)
ollama pull nomic-embed-text
ollama pull deepseek-v3.1:671b-cloud

# Verify installation
ollama list
```

### 6. Install Nginx
```bash
sudo apt-get install -y nginx

# Start and enable Nginx
sudo systemctl start nginx
sudo systemctl enable nginx

# Test Nginx
curl http://localhost  # Should return nginx welcome page
```

## Application Deployment

### 1. Clone Repository
```bash
# Switch to chatbot user
sudo su - chatbot

# Clone repository
cd /home/chatbot
git clone <your-repo-url> app
cd app
```

### 2. Set Up Virtual Environment
```bash
# Create virtual environment
python3.10 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
# Copy example environment file
cp .env.example .env

# Edit configuration
nano .env
```

Example production `.env`:
```env
# Site Configuration
SITE_ID=exportgenius
SITE_NAME=Export Genius
KB_CHUNKS_FILE=data/kb_exportgenius_chunks.json
FAISS_INDEX_FILE=data/faiss_exportgenius_normalized.index

# Redis (localhost on production server)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_redis_password_here
REDIS_TTL_DAYS=7

# Ollama (local installation)
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=deepseek-v3.1:671b-cloud
EMBEDDING_MODEL=nomic-embed-text

# API Server
API_HOST=0.0.0.0
API_PORT=8000

# Performance
DISABLE_CHECKPOINTING=false
ENABLE_PERFORMANCE_LOGGING=true

# Security (if using API tokens)
EXPORT_GENIUS_BEARER_TOKEN=your_token_here
MARKETINSIDE_BEARER_TOKEN=your_token_here
```

### 4. Verify Data Files
```bash
# Check data files exist
ls -lh data/

# Should see:
# - kb_exportgenius_chunks.json
# - faiss_exportgenius_normalized.index
# (or marketinside equivalents)
```

### 5. Test Application
```bash
# Activate virtual environment
source venv/bin/activate

# Test run
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000

# In another terminal, test
curl http://localhost:8000/api/health

# Stop test run (Ctrl+C)
```

## Systemd Service Configuration

### 1. Create Service File
```bash
sudo nano /etc/systemd/system/chatbot.service
```

Add the following:
```ini
[Unit]
Description=MI Chat Bot FastAPI Application
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=chatbot
Group=chatbot
WorkingDirectory=/home/chatbot/app
Environment="PATH=/home/chatbot/app/venv/bin"
Environment="PYTHONUNBUFFERED=1"

# Main command
ExecStart=/home/chatbot/app/venv/bin/uvicorn fastapi_chatbot:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info \
    --no-access-log

# Restart policy
Restart=always
RestartSec=10
StartLimitInterval=0

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/home/chatbot/app/data /home/chatbot/app/logs

# Resource limits
LimitNOFILE=65536
MemoryLimit=8G
CPUQuota=400%

[Install]
WantedBy=multi-user.target
```

### 2. Enable and Start Service
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable chatbot

# Start service
sudo systemctl start chatbot

# Check status
sudo systemctl status chatbot

# View logs
sudo journalctl -u chatbot -f
```

### 3. Service Management Commands
```bash
# Start
sudo systemctl start chatbot

# Stop
sudo systemctl stop chatbot

# Restart
sudo systemctl restart chatbot

# Status
sudo systemctl status chatbot

# Enable (auto-start on boot)
sudo systemctl enable chatbot

# Disable (don't auto-start)
sudo systemctl disable chatbot

# View logs (real-time)
sudo journalctl -u chatbot -f

# View logs (last 100 lines)
sudo journalctl -u chatbot -n 100

# View logs (since boot)
sudo journalctl -u chatbot -b
```

## Nginx Reverse Proxy

### 1. Create Nginx Configuration
```bash
sudo nano /etc/nginx/sites-available/chatbot
```

Add the following:
```nginx
# Upstream server
upstream chatbot_backend {
    server 127.0.0.1:8000 fail_timeout=30s;
    keepalive 32;
}

# HTTP server (will redirect to HTTPS)
server {
    listen 80;
    listen [::]:80;
    server_name your-domain.com www.your-domain.com;

    # Let's Encrypt challenge
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # Redirect all HTTP to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL certificates (configured by certbot)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL configuration (strong security)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Logging
    access_log /var/log/nginx/chatbot_access.log;
    error_log /var/log/nginx/chatbot_error.log;

    # Max body size (for large requests)
    client_max_body_size 10M;

    # Proxy to FastAPI backend
    location / {
        proxy_pass http://chatbot_backend;
        proxy_http_version 1.1;

        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for future streaming)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Buffering
        proxy_buffering off;
    }

    # Health check endpoint (no logging)
    location /api/health {
        proxy_pass http://chatbot_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        access_log off;
    }

    # Static files (if any)
    location /static/ {
        alias /home/chatbot/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### 2. Enable Configuration
```bash
# Test configuration
sudo nginx -t

# Create symlink
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/

# Reload Nginx
sudo systemctl reload nginx
```

## SSL/TLS with Let's Encrypt

### 1. Install Certbot
```bash
sudo apt-get install -y certbot python3-certbot-nginx
```

### 2. Obtain Certificate
```bash
# Make sure your domain points to your server IP
# Then run:
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Follow the prompts:
# - Enter email address
# - Agree to terms
# - Choose redirect HTTP to HTTPS (recommended)
```

### 3. Auto-Renewal
```bash
# Certbot automatically sets up renewal
# Test renewal process
sudo certbot renew --dry-run

# Check renewal timer
sudo systemctl status certbot.timer
```

### 4. Manual Renewal
```bash
# If needed, renew manually
sudo certbot renew

# Reload Nginx after renewal
sudo systemctl reload nginx
```

## Monitoring and Logging

### 1. Application Logs
```bash
# Real-time logs
sudo journalctl -u chatbot -f

# Recent logs
sudo journalctl -u chatbot -n 100 --no-pager

# Logs since boot
sudo journalctl -u chatbot -b

# Logs for specific time range
sudo journalctl -u chatbot --since "2024-01-01 00:00:00" --until "2024-01-01 23:59:59"
```

### 2. Nginx Logs
```bash
# Access logs
sudo tail -f /var/log/nginx/chatbot_access.log

# Error logs
sudo tail -f /var/log/nginx/chatbot_error.log
```

### 3. Redis Monitoring
```bash
# Redis CLI monitor (real-time commands)
redis-cli MONITOR

# Redis stats
redis-cli INFO stats

# Check memory usage
redis-cli INFO memory

# Check connected clients
redis-cli CLIENT LIST
```

### 4. System Resources
```bash
# CPU and memory usage
htop

# Disk usage
df -h

# Check service status
sudo systemctl status chatbot redis-server nginx

# Check open ports
sudo netstat -tulpn | grep -E ':(8000|6379|80|443)'
```

## Backup and Recovery

### 1. Backup Script
Create `/home/chatbot/backup.sh`:
```bash
#!/bin/bash
# MI Chat Bot Backup Script

BACKUP_DIR="/home/chatbot/backups"
DATE=$(date +%Y%m%d_%H%M%S)
APP_DIR="/home/chatbot/app"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup data files
tar -czf "$BACKUP_DIR/data_$DATE.tar.gz" -C "$APP_DIR" data/

# Backup configuration
cp "$APP_DIR/.env" "$BACKUP_DIR/env_$DATE.txt"

# Backup Redis database
redis-cli SAVE
cp /var/lib/redis/dump.rdb "$BACKUP_DIR/redis_$DATE.rdb"

# Keep only last 7 days of backups
find "$BACKUP_DIR" -type f -mtime +7 -delete

echo "Backup completed: $DATE"
```

Make executable:
```bash
chmod +x /home/chatbot/backup.sh
```

### 2. Automated Backups
```bash
# Add to crontab
crontab -e

# Add line (daily backup at 2 AM)
0 2 * * * /home/chatbot/backup.sh >> /home/chatbot/backup.log 2>&1
```

### 3. Restore from Backup
```bash
# Stop services
sudo systemctl stop chatbot

# Restore data
cd /home/chatbot/app
tar -xzf /home/chatbot/backups/data_YYYYMMDD_HHMMSS.tar.gz

# Restore Redis
sudo systemctl stop redis-server
sudo cp /home/chatbot/backups/redis_YYYYMMDD_HHMMSS.rdb /var/lib/redis/dump.rdb
sudo chown redis:redis /var/lib/redis/dump.rdb
sudo systemctl start redis-server

# Restart service
sudo systemctl start chatbot
```

## Scaling

### 1. Horizontal Scaling
Run multiple instances behind a load balancer:

```bash
# Instance 1
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --workers 4

# Instance 2
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8001 --workers 4
```

Update Nginx:
```nginx
upstream chatbot_backend {
    server 127.0.0.1:8000;
    server 127.0.0.1:8001;
    keepalive 32;
}
```

### 2. Redis Cluster
For high-availability, set up Redis cluster:
```bash
# Install Redis cluster
sudo apt-get install redis-tools

# Configure Redis cluster
# (Follow Redis cluster documentation)
```

### 3. Load Balancer
Use HAProxy or Nginx for load balancing:
```nginx
upstream chatbot_cluster {
    least_conn;
    server server1.example.com:8000 max_fails=3 fail_timeout=30s;
    server server2.example.com:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}
```

## Multi-Site Production Deployment

### Running Multiple Sites on Same Server

#### Site 1: Export Genius (Port 8000)
```bash
# Service file: /etc/systemd/system/chatbot-exportgenius.service
[Unit]
Description=Export Genius Chatbot
After=network.target redis-server.service

[Service]
Type=simple
User=chatbot
WorkingDirectory=/home/chatbot/app
Environment="PATH=/home/chatbot/app/venv/bin"
Environment="SITE_ID=exportgenius"
Environment="SITE_NAME=Export Genius"
Environment="REDIS_DB=0"
Environment="KB_CHUNKS_FILE=data/kb_exportgenius_chunks.json"
Environment="FAISS_INDEX_FILE=data/faiss_exportgenius_normalized.index"

ExecStart=/home/chatbot/app/venv/bin/uvicorn fastapi_chatbot:app \
    --host 0.0.0.0 --port 8000 --workers 4

Restart=always

[Install]
WantedBy=multi-user.target
```

#### Site 2: Market Inside (Port 8003)
```bash
# Service file: /etc/systemd/system/chatbot-marketinside.service
[Unit]
Description=Market Inside Chatbot
After=network.target redis-server.service

[Service]
Type=simple
User=chatbot
WorkingDirectory=/home/chatbot/app
Environment="PATH=/home/chatbot/app/venv/bin"
Environment="SITE_ID=marketinside"
Environment="SITE_NAME=Market Inside Data"
Environment="REDIS_DB=2"
Environment="KB_CHUNKS_FILE=data/kb_marketinside_chunks.json"
Environment="FAISS_INDEX_FILE=data/faiss_marketinside_normalized.index"

ExecStart=/home/chatbot/app/venv/bin/uvicorn fastapi_chatbot:app \
    --host 0.0.0.0 --port 8003 --workers 4

Restart=always

[Install]
WantedBy=multi-user.target
```

Enable both:
```bash
sudo systemctl enable chatbot-exportgenius chatbot-marketinside
sudo systemctl start chatbot-exportgenius chatbot-marketinside
```

## Production Checklist

Before going live:

- [ ] Redis is running and configured with persistence
- [ ] Ollama models are downloaded and working
- [ ] Data files (FAISS index, chunks) are present
- [ ] Environment variables are properly configured
- [ ] Systemd service is enabled and running
- [ ] Nginx is configured and running
- [ ] SSL certificates are installed and auto-renewing
- [ ] Firewall is configured (allow 80, 443; block 8000)
- [ ] Backups are scheduled
- [ ] Monitoring is set up
- [ ] Logs are being rotated
- [ ] Health check endpoint is responding
- [ ] Load testing has been performed
- [ ] Domain DNS is pointing to server

## Security Recommendations

1. **Firewall**: Only expose ports 80 and 443
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

2. **SSH**: Disable password auth, use key-based only
```bash
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
sudo systemctl restart sshd
```

3. **Redis**: Set password and bind to localhost only
```bash
sudo nano /etc/redis/redis.conf
# Set: requirepass your_strong_password
# Set: bind 127.0.0.1
```

4. **Updates**: Enable automatic security updates
```bash
sudo apt-get install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

5. **Rate Limiting**: Configure in Nginx
```nginx
limit_req_zone $binary_remote_addr zone=chatbot_limit:10m rate=10r/s;

location / {
    limit_req zone=chatbot_limit burst=20 nodelay;
    # ... rest of config
}
```

---

**Deployment Time**: ~30 minutes for single site
**Difficulty**: Intermediate
**Maintenance**: Low (automated updates and backups)

For questions or issues, refer to the [README](README.md) or contact the development team.
