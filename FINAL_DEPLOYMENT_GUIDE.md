# EG Chatbot - Complete Deployment Guide

**Deploy Backend API + Frontend Widget on Linux Server with PM2**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     YOUR LINUX SERVER (16GB RAM)                    │
│                 (chatbot.exportgenius.in)                           │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                        NGINX                                 │   │
│  │              (Reverse Proxy + Static Files)                  │   │
│  │                                                              │   │
│  │   Port 80/443                                                │   │
│  │   ├── /api/*          → FastAPI (8000)                      │   │
│  │   └── /chat-widget.js → Static file (widget-dist/)          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                           │                                         │
│              ┌────────────┴────────────┐                           │
│              ▼                         ▼                            │
│  ┌───────────────────┐    ┌───────────────────────────┐            │
│  │   PM2: Backend    │    │   Static: Widget JS       │            │
│  │   eg-chatbot-api  │    │   /opt/eg-chatbot/        │            │
│  │   Port 8000       │    │   widget-dist/            │            │
│  │   2 Workers       │    │   chat-widget.js          │            │
│  │   (~6-8GB RAM)    │    │   (Served by Nginx)       │            │
│  │                   │    └───────────────────────────┘            │
│  │   FastAPI +       │                                              │
│  │   LangGraph +     │    ┌───────────────────────────┐            │
│  │   FAISS           │    │   Redis (Session Cache)   │            │
│  └───────────────────┘    │   Port 6379               │            │
│         │    │            │   (~500MB RAM)            │            │
│         │    └────────────►───────────────────────────┘            │
│         │                                                           │
│         │                 ┌───────────────────────────┐            │
│         │                 │   MySQL (FAQ Database)    │            │
│         └─────────────────►   Port 3306               │            │
│                           │   (~200MB RAM)            │            │
│                           │   Stores: FAQ questions,  │            │
│                           │   page configs, analytics │            │
│                           └───────────────────────────┘            │
│                                                                     │
│  MEMORY BREAKDOWN (16GB Server):                                   │
│  • FastAPI + FAISS (2 workers): ~6-8GB                             │
│  • Redis: ~500MB                                                    │
│  • MySQL: ~200MB                                                    │
│  • Nginx + OS: ~2GB                                                 │
│  • Buffer: ~5-6GB                                                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   YOUR NEXT.JS WEBSITE                              │
│               (Vercel / Your hosting)                               │
│                                                                     │
│   <ChatbotWidget />  →  Loads chat-widget.js from your server      │
│                      →  Makes API calls to /api/*                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## STEP 1: Server Preparation (One-Time)

### 1.1 Connect to Your Server

```bash
ssh deploy@YOUR_SERVER_IP
# Or
ssh root@YOUR_SERVER_IP
```

### 1.2 Install Required Software

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python 3.10+
sudo apt-get install -y python3 python3-pip python3-venv python3-dev

# Install Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install PM2
sudo npm install -g pm2

# Install Redis
sudo apt-get install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Install MySQL (for FAQ/Suggested Questions feature)
sudo apt-get install -y mysql-server
sudo systemctl enable mysql
sudo systemctl start mysql

# Secure MySQL installation (set root password, remove test DB, etc.)
sudo mysql_secure_installation

# Install Nginx
sudo apt-get install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx

# Install build tools
sudo apt-get install -y build-essential git curl

# Verify installations
python3 --version    # Should be 3.10+
node --version       # Should be 20.x
pm2 --version        # Should show version
redis-cli ping       # Should return PONG
nginx -v             # Should show version
mysql --version      # Should show version (8.x recommended)
```

### 1.3 Create Directory Structure

```bash
# Create app directory
sudo mkdir -p /opt/eg-chatbot
sudo mkdir -p /var/log/eg-chatbot

# Set ownership (change 'deploy' to your user)
sudo chown -R deploy:deploy /opt/eg-chatbot
sudo chown -R deploy:deploy /var/log/eg-chatbot

# Create Python virtual environment
cd /opt/eg-chatbot
python3 -m venv venv
source venv/bin/activate

# Create widget dist folder
mkdir -p widget-dist  
```

### 1.4 Setup SSH Keys for CI/CD

```bash
# Generate SSH key (as deploy user)
ssh-keygen -t rsa -b 4096 -C "deploy@eg-chatbot" -f ~/.ssh/id_rsa -N ""

# Add to authorized_keys
cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# SAVE PRIVATE KEY - You'll need this for GitHub
cat ~/.ssh/id_rsa
# Copy entire content including BEGIN and END lines
```

### 1.5 Setup MySQL Database (For FAQ Feature)

The chatbot uses MySQL to store page-specific suggested questions (FAQ feature).x`

```bash
# Login to MySQL as root
sudo mysql -u root -p

# Create database and user
CREATE DATABASE chatbot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# Create dedicated user (recommended for production)
CREATE USER 'chatbot_user'@'localhost' IDENTIFIED BY 'your_secure_password_here';
GRANT ALL PRIVILEGES ON chatbot.* TO 'chatbot_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

**Import the schema:**

```bash
# From the project directory, import the schema
mysql -u root -p chatbot < /opt/eg-chatbot/chatbot/database/schema.sql

# Verify tables were created
mysql -u root -p -e "USE chatbot; SHOW TABLES;"
```

Expected output:
```
+-------------------+
| Tables_in_chatbot |
+-------------------+
| faq               |
| pages             |
+-------------------+
```

**Verify FAQ data:**

```bash
mysql -u root -p -e "SELECT COUNT(*) as total_faqs FROM chatbot.faq;"
mysql -u root -p -e "SELECT page_name, url_pattern FROM chatbot.pages;"
```

---

## STEP 2: Configure Nginx

### 2.1 Create Nginx Configuration

```bash
# Copy the pre-configured nginx file from your repo
sudo cp /opt/eg-chatbot/nginx/chatbot.conf /etc/nginx/sites-available/eg-chatbot

# Or create manually:
sudo nano /etc/nginx/sites-available/eg-chatbot
```

Paste this configuration (or use the `nginx/chatbot.conf` file in the repo):

```nginx
# Rate limiting
limit_req_zone $binary_remote_addr zone=chatbot_api:10m rate=10r/s;

upstream chatbot_api {
    server 127.0.0.1:8000 fail_timeout=30s;
    keepalive 32;
}

server {
    listen 80;
    listen [::]:80;
    server_name chatbot.exportgenius.in;  # CHANGE THIS to your domain

    # API Endpoints
    location /api/ {
        limit_req zone=chatbot_api burst=20 nodelay;

        proxy_pass http://chatbot_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Streaming support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts for LLM
        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
        proxy_buffering off;

        # CORS
        add_header Access-Control-Allow-Origin * always;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Content-Type, Authorization" always;

        if ($request_method = OPTIONS) {
            add_header Access-Control-Allow-Origin *;
            add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
            add_header Access-Control-Allow-Headers "Content-Type, Authorization";
            return 204;
        }
    }

    # Widget Static File
    location = /chat-widget.js {
        alias /opt/eg-chatbot/widget-dist/chat-widget.js;
        expires 1h;
        add_header Cache-Control "public";
        add_header Access-Control-Allow-Origin * always;
        types { application/javascript js; }
    }

    # Health check
    location = /api/health {
        proxy_pass http://chatbot_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        access_log off;
    }

    # Swagger docs
    location /docs {
        proxy_pass http://chatbot_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    location /openapi.json {
        proxy_pass http://chatbot_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    # Logging
    access_log /var/log/nginx/chatbot_access.log;
    error_log /var/log/nginx/chatbot_error.log;
}
```

### 2.2 Enable Configuration

```bash
# Test config
sudo nginx -t

# Enable site
sudo ln -sf /etc/nginx/sites-available/eg-chatbot /etc/nginx/sites-enabled/

# Remove default if exists
sudo rm -f /etc/nginx/sites-enabled/default

# Reload Nginx
sudo systemctl reload nginx
```

### 2.3 Setup SSL (Optional but Recommended)

```bash
# Install Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d chatbot.exportgenius.in

# Auto-renewal test
sudo certbot renew --dry-run
```

---

## STEP 3: GitHub Repository Setup

### 3.1 Add GitHub Secrets

Go to: **GitHub → Your Repo → Settings → Secrets and variables → Actions**

Add these 4 secrets:

| Secret Name | Value |
|-------------|-------|
| `SSH_PRIVATE_KEY` | Content of `/home/deploy/.ssh/id_rsa` (full private key) |
| `SERVER_IP` | Your server IP (e.g., `123.45.67.89`) |
| `SERVER_USER` | `deploy` |
| `DEPLOY_PATH` | `/opt/eg-chatbot` |

### 3.2 Push Code to GitHub

```bash
# On your LOCAL machine
cd "C:\MI Ticket\MI Chat Bot\Scrapper Function"

git add .
git commit -m "Update deployment configuration"
git push origin main
```

---

## STEP 4: First Manual Deployment

### 4.1 Copy Files to Server

```bash
# From your LOCAL machine (PowerShell/Git Bash)
# Use SCP to copy files

scp -r "C:\MI Ticket\MI Chat Bot\Scrapper Function\*" deploy@YOUR_SERVER_IP:/opt/eg-chatbot/

# Or use rsync if available
rsync -avz --exclude '.git' --exclude 'venv' --exclude '__pycache__' \
  "C:\MI Ticket\MI Chat Bot\Scrapper Function/" deploy@YOUR_SERVER_IP:/opt/eg-chatbot/
```

### 4.2 Setup on Server

```bash
# SSH to server
ssh deploy@YOUR_SERVER_IP

# Go to app directory
cd /opt/eg-chatbot

# Activate virtual environment
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file
nano .env
```

Paste your .env content (example):

```env
# Site Configuration
SITE_ID=exportgenius
SITE_NAME=Export Genius
KB_CHUNKS_FILE=data/kb_exportgenius_chunks.json
FAISS_INDEX_FILE=data/faiss_exportgenius_normalized.index

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_TTL_DAYS=7

# Ollama (Cloud API)
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_API_KEY=your-api-key-here
LLM_MODEL=deepseek-v3.1:671b-cloud
EMBEDDING_MODEL=nomic-embed-text

# API
API_HOST=0.0.0.0
API_PORT=8000

# Tokens (optional)
EXPORT_GENIUS_BEARER_TOKEN=your-token

# MySQL Configuration (for FAQ/Suggested Questions feature)
FAQ_ENABLED=true
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=chatbot_user          # Or 'root' for simple setups
MYSQL_PASSWORD=your-password     # Password set during MySQL setup
MYSQL_DATABASE=chatbot
MYSQL_POOL_SIZE=5
```

Save and exit (Ctrl+X, Y, Enter)

### 4.3 Build Frontend Widget

```bash
# On server
cd /opt/eg-chatbot/frontend

# Install Node dependencies
npm install

# Build widget
npm run build

# Copy to widget-dist
mkdir -p ../widget-dist
cp ../backend/assets/chat-widget.js ../widget-dist/

# Verify
ls -la ../widget-dist/
# Should show chat-widget.js
```

### 4.4 Start PM2 Services

```bash
# Go back to app root
cd /opt/eg-chatbot

# Start with PM2
pm2 start ecosystem.config.js

# Save PM2 configuration
pm2 save

# Setup PM2 to start on boot
pm2 startup
# Run the command it outputs (starts with sudo)

# Check status
pm2 status
```

### 4.5 Verify Deployment

```bash
# Check API health
curl http://localhost:8000/api/health

# Check via Nginx
curl http://YOUR_SERVER_IP/api/health

# Check widget file
curl -I http://YOUR_SERVER_IP/chat-widget.js

# View logs
pm2 logs eg-chatbot-api
```

---

## STEP 5: Integrate with Next.js Website

### 5.1 Copy Widget Component

Copy `nextjs-integration/chatbot-widget.tsx` to your Next.js project:

```
your-nextjs-project/
├── components/
│   └── chatbot-widget/
│       └── chatbot-widget.tsx   ← Copy here
```

### 5.2 Add Environment Variables

Add to your Next.js `.env.local`:

```env
# Chatbot Configuration
NEXT_PUBLIC_CHATBOT_API_URL=https://chatbot.exportgenius.in
NEXT_PUBLIC_CHATBOT_WIDGET_URL=https://chatbot.exportgenius.in/chat-widget.js
```

### 5.3 Update Layout

In your `app/layout.tsx`:

```tsx
import ChatbotWidget from "@/components/chatbot-widget/chatbot-widget"

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* Your existing layout */}
        {children}

        {/* Chatbot Widget - renders at bottom right */}
        <ChatbotWidget />
      </body>
    </html>
  )
}
```

### 5.4 Handle Schedule Demo (in ClientLayout)

Your ClientLayout should listen for widget events:

```tsx
'use client'

import { useState, useEffect } from 'react'
import ScheduleDemo from '@/components/schedule-demo'

export default function ClientLayout({ children }) {
  const [showScheduleDemo, setShowScheduleDemo] = useState(false)

  useEffect(() => {
    const handleChatWidgetEvent = (event: CustomEvent) => {
      if (event.detail?.action =. == 'openScheduleDemo') {
        setShowScheduleDemo(true)
      }
    }

    window.addEventListener('chatWidget:action', handleChatWidgetEvent)
    return () => window.removeEventListener('chatWidget:action', handleChatWidgetEvent)
  }, [])

  return (
    <>
      {children}
      {showScheduleDemo && (
        <ScheduleDemo handleBackdropClick={() => setShowScheduleDemo(false)} />
      )}
    </>
  )
}
```

---

## STEP 6: Automated Deployments (CI/CD)

After initial setup, future deployments are automatic:

```bash
# Make changes locally
git add .
git commit -m "Your changes"
git push origin main

# GitHub Actions will:
# 1. Build frontend widget
# 2. Copy files to server
# 3. Install dependencies
# 4. Reload PM2
# 5. Run health check
```

Monitor in: **GitHub → Actions tab**

---

## Quick Reference Commands

### PM2 Commands

```bash
pm2 status                    # Check status
pm2 logs eg-chatbot-api       # View logs
pm2 restart eg-chatbot-api    # Restart API
pm2 reload ecosystem.config.js # Reload config
pm2 monit                     # Monitor resources
pm2 save                      # Save current state
```

### Service Checks

```bash
# Check all services
pm2 status
sudo systemctl status nginx
sudo systemctl status redis-server
sudo systemctl status mysql

# Health checks
curl http://localhost:8000/api/health
curl http://YOUR_DOMAIN/api/health
curl http://YOUR_DOMAIN/chat-widget.js -I

# Check MySQL connection
mysql -u chatbot_user -p -e "SELECT 'MySQL OK' as status;"

# View logs
pm2 logs eg-chatbot-api --lines 100
tail -f /var/log/nginx/chatbot_access.log
tail -f /var/log/nginx/chatbot_error.log
```

### Rebuild Widget

```bash
cd /opt/eg-chatbot/frontend
npm run build
cp ../backend/assets/chat-widget.js ../widget-dist/
```

---

## URLs After Deployment

| Service | URL |
|---------|-----|
| API Health | `https://chatbot.exportgenius.in/api/health` |
| API Docs | `https://chatbot.exportgenius.in/docs` |
| Widget JS | `https://chatbot.exportgenius.in/chat-widget.js` |
| Chat Endpoint | `POST https://chatbot.exportgenius.in/api/chat` |
| Init Endpoint | `POST https://chatbot.exportgenius.in/api/init` |

---

## Troubleshooting

### High Memory Usage (98%+)

If your server memory usage is very high:

```bash
# Check what's using memory
ps aux --sort=-%mem | head -10

# Check PM2 processes
pm2 monit
```

**Common causes:**

1. **Too many uvicorn workers** - Each worker loads FAISS index (~3-4GB each)
   ```bash
   # Check ecosystem.config.js - should be 2 workers for 16GB RAM
   # args: 'fastapi_chatbot:app --host 0.0.0.0 --port 8000 --workers 2'

   # Restart with updated config
   pm2 restart eg-chatbot-api
   ```

2. **Memory leak** - Restart PM2 periodically
   ```bash
   # The ecosystem.config.js has max_memory_restart: '4G'
   # This auto-restarts if a worker exceeds 4GB
   ```

3. **Check Redis memory**
   ```bash
   redis-cli INFO memory | grep used_memory_human
   ```

**Recommended memory settings for 16GB server:**
- Uvicorn workers: 2 (not 4)
- max_memory_restart: 4G
- Redis maxmemory: 1gb (set in /etc/redis/redis.conf)

---

### Widget Not Loading

```bash
# Check if file exists
ls -la /opt/eg-chatbot/widget-dist/

# Rebuild if missing
cd /opt/eg-chatbot/frontend
npm run build
cp ../backend/assets/chat-widget.js ../widget-dist/

# Check Nginx serving
curl -I http://YOUR_DOMAIN/chat-widget.js
```

### API Errors

```bash
# Check PM2 logs
pm2 logs eg-chatbot-api --err

# Check if running
pm2 status

# Restart
pm2 restart eg-chatbot-api

# Check Redis
redis-cli ping
```

### CORS Issues

Ensure Nginx has CORS headers (already in config above).

### 502 Bad Gateway

```bash
# API not running
pm2 restart eg-chatbot-api

# Check port
sudo lsof -i :8000
```

### MySQL Connection Issues

If FAQ/Suggested Questions aren't working:

```bash
# Check MySQL is running
sudo systemctl status mysql

# Test connection
mysql -u chatbot_user -p -e "SELECT 1;"

# Check database exists
mysql -u root -p -e "SHOW DATABASES LIKE 'chatbot';"

# Check tables exist
mysql -u root -p chatbot -e "SHOW TABLES;"

# Verify FAQ data
mysql -u root -p chatbot -e "SELECT COUNT(*) FROM faq;"

# Check PM2 logs for MySQL errors
pm2 logs eg-chatbot-api --lines 50 | grep -i mysql
```

**Common MySQL errors:**

1. **"Access denied"** - Wrong username/password in `.env`
   ```bash
   # Reset user password
   sudo mysql -u root -p
   ALTER USER 'chatbot_user'@'localhost' IDENTIFIED BY 'new_password';
   FLUSH PRIVILEGES;
   ```

2. **"Unknown database 'chatbot'"** - Database not created
   ```bash
   sudo mysql -u root -p -e "CREATE DATABASE chatbot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
   mysql -u root -p chatbot < /opt/eg-chatbot/chatbot/database/schema.sql
   ```

3. **"Table doesn't exist"** - Schema not imported
   ```bash
   mysql -u root -p chatbot < /opt/eg-chatbot/chatbot/database/schema.sql
   ```

4. **"Can't connect to MySQL server"** - MySQL not running
   ```bash
   sudo systemctl start mysql
   sudo systemctl enable mysql
   ```

### FAQ Feature Not Working

If suggested questions don't appear in the chat widget:

1. **Check FAQ_ENABLED in .env:**
   ```bash
   grep FAQ_ENABLED /opt/eg-chatbot/.env
   # Should show: FAQ_ENABLED=true
   ```

2. **Verify URL patterns match your site:**
   ```bash
   mysql -u root -p chatbot -e "SELECT page_key, url_pattern FROM pages;"
   ```

3. **Check API logs for FAQ messages:**
   ```bash
   pm2 logs eg-chatbot-api | grep -i faq
   # Should show: [FAQ] ✓ MySQL connection pool initialized
   ```

4. **Test FAQ endpoint directly:**
   ```bash
   curl -X POST http://localhost:8000/api/init \
     -H "Content-Type: application/json" \
     -d '{"session_id": "test", "page_url": "https://www.marketinsidedata.com/"}'
   ```

---

## Deployment Checklist

### Server Software
- [ ] Python 3.10+ installed
- [ ] Node.js 20.x installed
- [ ] PM2 installed globally
- [ ] Redis server installed and running
- [ ] MySQL server installed and running
- [ ] Nginx installed and running

### Application Setup
- [ ] `/opt/eg-chatbot` directory created with correct permissions
- [ ] Virtual environment created and dependencies installed
- [ ] `.env` file configured on server with all variables

### Database Setup
- [ ] MySQL `chatbot` database created
- [ ] MySQL user created with proper permissions
- [ ] Schema imported (`schema.sql`)
- [ ] FAQ data verified in database

### Web Server
- [ ] Nginx config in `/etc/nginx/sites-enabled/`
- [ ] SSL certificate installed (recommended)
- [ ] CORS headers configured

### CI/CD
- [ ] GitHub Secrets configured (4 secrets: SSH_PRIVATE_KEY, SERVER_IP, SERVER_USER, DEPLOY_PATH)

### Deployment Verification
- [ ] Frontend widget built and in `widget-dist/`
- [ ] PM2 started and saved (`pm2 save`)
- [ ] PM2 startup configured (`pm2 startup`)
- [ ] Health check passing (`/api/health`)
- [ ] Widget accessible at `https://YOUR_DOMAIN/chat-widget.js`
- [ ] FAQ feature working (suggested questions appearing)

### Frontend Integration
- [ ] Next.js env vars configured
- [ ] ChatbotWidget component added to layout

---

**Your chatbot is now deployed!** 🚀
