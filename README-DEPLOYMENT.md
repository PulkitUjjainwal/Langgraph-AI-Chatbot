# EG Chatbot API - Complete Deployment Guide

**End-to-end deployment with GitHub Actions CI/CD + PM2 on Linux server**

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Server Initial Setup](#server-initial-setup)
3. [Local Setup (Your Machine)](#local-setup-your-machine)
4. [GitHub Repository Setup](#github-repository-setup)
5. [PM2 Configuration](#pm2-configuration)
6. [CI/CD Pipeline Setup](#cicd-pipeline-setup)
7. [First Deployment](#first-deployment)
8. [Monitoring & Management](#monitoring--management)
9. [Troubleshooting](#troubleshooting)
10. [Daily Operations](#daily-operations)

---

## 🎯 Prerequisites

### What You Need

- **Linux Server:** Ubuntu 20.04+ / Debian 11+ (VPS, EC2, etc.)
- **Server Specs:**
  - Minimum: 2 CPU cores, 4GB RAM, 20GB disk
  - Recommended: 4 CPU cores, 8GB RAM, 50GB disk (for 10K users)
- **Domain Name:** Optional but recommended
- **SSH Access:** Root or sudo access to server
- **GitHub Account:** For CI/CD pipeline
- **Local Machine:** Windows/Mac/Linux with Git installed

### Server Access Info You'll Need

- Server IP address
- SSH username and password (initially)
- Domain name (if you have one)

---

## 🖥️ STEP 1: Server Initial Setup

### 1.1 Connect to Your Server

```bash
# From your local machine
ssh root@YOUR_SERVER_IP

# Or if you have a user
ssh username@YOUR_SERVER_IP
```

### 1.2 Update System

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### 1.3 Install Python 3.10+

```bash
# Install Python
sudo apt-get install -y python3 python3-pip python3-venv

# Verify version
python3 --version  # Should be 3.10+
```

### 1.4 Install System Dependencies

```bash
sudo apt-get install -y \
    build-essential \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    git \
    curl \
    nginx \
    ufw
```

### 1.5 Install Redis

```bash
# Install Redis
sudo apt-get install -y redis-server

# Start Redis
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Verify
redis-cli ping  # Should return "PONG"
```

### 1.6 Install Ollama

```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull your model
ollama pull deepseek-v3.1:671b-cloud

# Verify
ollama list
```

### 1.7 Install Node.js and PM2

```bash
# Install Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify Node
node --version  # Should be v20.x
npm --version

# Install PM2 globally
sudo npm install -g pm2

# Verify PM2
pm2 --version
```

### 1.8 Create Deployment User

```bash
# Create user for deployment
sudo useradd -m -s /bin/bash deploy
sudo usermod -aG sudo deploy

# Set password (you'll be prompted)
sudo passwd deploy

# Switch to deploy user
sudo su - deploy
```

### 1.9 Setup Application Directory

```bash
# Create directories
sudo mkdir -p /opt/eg-chatbot
sudo mkdir -p /var/log/eg-chatbot

# Set ownership
sudo chown -R deploy:deploy /opt/eg-chatbot
sudo chown -R deploy:deploy /var/log/eg-chatbot

# Navigate to app directory
cd /opt/eg-chatbot

# Create virtual environment
python3 -m venv venv

# Activate venv
source venv/bin/activate

# Verify
which python  # Should show /opt/eg-chatbot/venv/bin/python
```

### 1.10 Setup SSH Key for CI/CD

```bash
# Generate SSH key pair (on your server as deploy user)
ssh-keygen -t rsa -b 4096 -C "deploy@eg-chatbot" -f ~/.ssh/id_rsa -N ""

# View public key (save this - you'll need it)
cat ~/.ssh/id_rsa.pub

# View private key (save this for GitHub Secrets)
cat ~/.ssh/id_rsa

# Add public key to authorized_keys
cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

**⚠️ IMPORTANT:** Save both keys securely. You'll add the private key to GitHub Secrets.

### 1.11 Configure Firewall

```bash
# Allow SSH, HTTP, HTTPS
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw --force enable

# Check status
sudo ufw status
```

---

## 💻 STEP 2: Local Setup (Your Machine)

### 2.1 Organize Your Project

On your local machine, ensure your project structure looks like this:

```
eg-chatbot/
├── fastapi_chatbot.py
├── redis_memory.py
├── hostility_detector.py
├── web_scraper.py
├── requirements.txt
├── .env.example
├── .gitignore
├── ecosystem.config.js       # You'll create this
├── data/
│   └── kb_chunks.json
└── .github/
    └── workflows/
        └── deploy.yml         # You'll create this
```

### 2.2 Create `.env.example`

Create this file (DON'T commit actual `.env` with secrets):

```bash
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_TTL_DAYS=7

# LLM Configuration
LLM_MODEL=deepseek-v3.1:671b-cloud
OLLAMA_BASE_URL=http://localhost:11434

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
```

### 2.3 Create `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# Environment
.env

# Logs
*.log
logs/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Test files
test_*.py
```

### 2.4 Configure `ecosystem.config.js`

**⚠️ IMPORTANT:** If you already have `ecosystem.config.js`, verify it has the correct paths.

**If you DON'T have it**, create this file:

```javascript
// PM2 Configuration for EG Chatbot API
module.exports = {
  apps: [
    {
      name: 'eg-chatbot-api',
      script: '/opt/eg-chatbot/venv/bin/uvicorn',
      args: 'fastapi_chatbot:app --host 0.0.0.0 --port 8000 --workers 4',
      cwd: '/opt/eg-chatbot',
      interpreter: '/opt/eg-chatbot/venv/bin/python3',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      watch: false,
      max_memory_restart: '2G',

      env: {
        NODE_ENV: 'production',
      },

      error_file: '/var/log/eg-chatbot/error.log',
      out_file: '/var/log/eg-chatbot/out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,

      restart_delay: 4000,
      max_restarts: 10,
      min_uptime: '10s',
      kill_timeout: 5000,
    },
  ],
};
```

**✅ Configuration Checklist - Verify These Values:**

| Setting | Current Value | What It Should Be |
|---------|---------------|-------------------|
| `name` | `eg-chatbot-api` | ✅ Keep as is |
| `script` | `/opt/eg-chatbot/venv/bin/uvicorn` | ✅ Keep as is |
| `cwd` | `/opt/eg-chatbot` | ✅ Keep as is |
| `interpreter` | `/opt/eg-chatbot/venv/bin/python3` | ✅ Keep as is |
| `error_file` | `/var/log/eg-chatbot/error.log` | ✅ Keep as is |
| `out_file` | `/var/log/eg-chatbot/out.log` | ✅ Keep as is |

**If your file has different paths (like `/opt/mi-chatbot`), change them to `/opt/eg-chatbot`**

**⚠️ Common Issue:** If your ecosystem.config.js has placeholders like `your-server-ip` or `yourusername/repo.git`, **you can ignore/delete that deployment section** - we're using GitHub Actions instead!

### 2.5 Create `.github/workflows/deploy.yml`

Create GitHub Actions workflow:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup SSH
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.SSH_PRIVATE_KEY }}

      - name: Add server to known hosts
        run: |
          mkdir -p ~/.ssh
          ssh-keyscan -H ${{ secrets.SERVER_IP }} >> ~/.ssh/known_hosts

      - name: Deploy to server
        run: |
          echo "🚀 Deploying to server..."

          # Sync files
          rsync -avz --delete \
            --exclude '.git' \
            --exclude '.github' \
            --exclude '__pycache__' \
            --exclude '*.pyc' \
            --exclude 'venv' \
            --exclude '.env' \
            --exclude 'test_*.py' \
            ./ ${{ secrets.SERVER_USER }}@${{ secrets.SERVER_IP }}:${{ secrets.DEPLOY_PATH }}/

          # Deploy on server
          ssh ${{ secrets.SERVER_USER }}@${{ secrets.SERVER_IP }} << 'ENDSSH'
            cd ${{ secrets.DEPLOY_PATH }}
            source venv/bin/activate
            pip install --upgrade pip
            pip install -r requirements.txt
            pm2 reload ecosystem.config.js --env production
            pm2 save
          ENDSSH

      - name: Health check
        run: |
          sleep 10
          curl --fail http://${{ secrets.SERVER_IP }}:8000/health
          echo "✅ Deployment successful!"
```

---

## 🔑 STEP 3: GitHub Repository Setup

### 3.1 Create GitHub Repository

1. Go to GitHub.com
2. Click "New Repository"
3. Name: `eg-chatbot` (or your choice)
4. Make it **Private** (recommended)
5. Click "Create Repository"

### 3.2 Add GitHub Secrets

Go to: **Repository → Settings → Secrets and variables → Actions → New repository secret**

Add these 4 secrets:

| Secret Name | Value | Example |
|-------------|-------|---------|
| `SSH_PRIVATE_KEY` | Content of `/home/deploy/.ssh/id_rsa` from server | `-----BEGIN RSA PRIVATE KEY-----...` |
| `SERVER_IP` | Your server IP address | `123.45.67.89` |
| `SERVER_USER` | Deployment user | `deploy` |
| `DEPLOY_PATH` | Application directory on server | `/opt/eg-chatbot` |

**How to get SSH_PRIVATE_KEY:**

```bash
# On your server
cat /home/deploy/.ssh/id_rsa
# Copy EVERYTHING including BEGIN and END lines
```

### 3.3 Push Code to GitHub

```bash
# On your local machine, in project directory
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin git@github.com:yourusername/eg-chatbot.git
git push -u origin main
```

### 3.4 Pre-Deployment Verification ✅

**Before deploying, verify everything is configured correctly:**

```bash
# On your LOCAL machine

# 1. Check ecosystem.config.js paths
grep "/opt/eg-chatbot" ecosystem.config.js
# Should show multiple lines with /opt/eg-chatbot paths

# 2. Check if .github/workflows/deploy.yml exists
ls .github/workflows/deploy.yml

# 3. Check if required files exist
ls fastapi_chatbot.py redis_memory.py hostility_detector.py

# 4. Verify GitHub Secrets are set
# Go to: GitHub → Repository → Settings → Secrets
# Confirm all 4 secrets exist:
# - SSH_PRIVATE_KEY
# - SERVER_IP
# - SERVER_USER
# - DEPLOY_PATH
```

**Checklist:**
- [ ] `ecosystem.config.js` has correct paths (`/opt/eg-chatbot`)
- [ ] `.github/workflows/deploy.yml` file exists
- [ ] All Python files present (fastapi_chatbot.py, redis_memory.py, etc.)
- [ ] `requirements.txt` exists
- [ ] `data/kb_chunks.json` exists
- [ ] GitHub repository created
- [ ] All 4 GitHub Secrets added
- [ ] Code pushed to GitHub main branch
- [ ] Server setup completed (STEP 1)

**If all checkboxes ✅, proceed to deployment!**

---

## 🚀 STEP 4: First Deployment

### 4.1 Manual First Deploy (One-Time)

Since CI/CD needs the app directory to exist first, do manual first deploy:

```bash
# On your LOCAL machine

# 1. Copy files to server
scp -r * deploy@YOUR_SERVER_IP:/opt/eg-chatbot/

# 2. SSH to server
ssh deploy@YOUR_SERVER_IP

# 3. Setup on server
cd /opt/eg-chatbot
source venv/bin/activate

# 4. Create .env file
nano .env
# Paste the content from .env.example and save (Ctrl+X, Y, Enter)

# 5. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 6. Test the application
python3 fastapi_chatbot.py
# Press Ctrl+C after verification

# 7. Start with PM2
pm2 start ecosystem.config.js
pm2 save
pm2 startup  # Follow the command it gives you

# 8. Check status
pm2 status
pm2 logs eg-chatbot-api
```

### 4.2 Verify Deployment

```bash
# Check if app is running
curl http://localhost:8000/health

# Should return something like:
# {"status":"healthy","kb_loaded":true,...}
```

### 4.3 Setup Nginx (Optional but Recommended)

```bash
# Create Nginx config
sudo nano /etc/nginx/sites-available/eg-chatbot
```

Paste this:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Change this

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }
}
```

Enable site:

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/eg-chatbot /etc/nginx/sites-enabled/

# Test config
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### 4.4 Setup SSL (Optional but Recommended)

```bash
# Install Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is automatic, verify with:
sudo certbot renew --dry-run
```

---

## 🔄 STEP 5: Automated Deployment (CI/CD)

### 5.1 How It Works

Once setup is complete:

```
You push to GitHub → GitHub Actions triggered →
Files synced to server → Dependencies installed →
PM2 reloads app → Health check → ✅ Done!
```

### 5.2 Make Changes and Deploy

```bash
# On your local machine

# 1. Make changes to your code
nano fastapi_chatbot.py  # Make your changes

# 2. Commit changes
git add .
git commit -m "Updated chat responses"

# 3. Push to trigger deployment
git push origin main

# 4. Watch deployment in GitHub
# Go to: Repository → Actions → See the workflow running
```

### 5.3 Monitor Deployment

1. Go to GitHub repository
2. Click "Actions" tab
3. See your workflow running
4. Green ✅ = Success
5. Red ❌ = Failed (check logs)

---

## 📊 STEP 6: Monitoring & Management

### 6.1 PM2 Commands

```bash
# View status
pm2 status

# View logs (live)
pm2 logs eg-chatbot-api

# View logs (last 100 lines)
pm2 logs eg-chatbot-api --lines 100

# Restart app
pm2 restart eg-chatbot-api

# Stop app
pm2 stop eg-chatbot-api

# Start app
pm2 start ecosystem.config.js

# Delete from PM2
pm2 delete eg-chatbot-api

# Monitor resources
pm2 monit

# Save current PM2 list
pm2 save

# View detailed info
pm2 show eg-chatbot-api
```

### 6.2 Application Logs

```bash
# View error logs
tail -f /var/log/eg-chatbot/error.log

# View output logs
tail -f /var/log/eg-chatbot/out.log

# Search logs
grep "ERROR" /var/log/eg-chatbot/error.log
```

### 6.3 System Monitoring

```bash
# Check system resources
htop

# Check disk usage
df -h

# Check Redis
redis-cli info memory

# Check Ollama
ollama ps

# Check Nginx
sudo systemctl status nginx
```

### 6.4 Health Checks

```bash
# Check API health
curl http://localhost:8000/health

# Check from outside (if Nginx is setup)
curl http://your-domain.com/health

# Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello","session_id":"test"}'
```

---

## 🔧 STEP 7: Troubleshooting

### Issue: PM2 app crashes

```bash
# Check logs
pm2 logs eg-chatbot-api --err

# Common causes:
# 1. Redis not running
sudo systemctl status redis-server
sudo systemctl start redis-server

# 2. Ollama not running
ollama list

# 3. Missing dependencies
cd /opt/eg-chatbot
source venv/bin/activate
pip install -r requirements.txt

# 4. Port already in use
sudo lsof -i :8000
# Kill process if needed: sudo kill <PID>

# Restart app
pm2 restart eg-chatbot-api
```

### Issue: CI/CD deployment fails

```bash
# 1. Check GitHub Actions logs
# Go to: Repository → Actions → Click failed workflow → View logs

# 2. Verify SSH access
ssh deploy@YOUR_SERVER_IP

# 3. Check GitHub Secrets
# Verify all 4 secrets are set correctly

# 4. Check server disk space
df -h

# 5. Manually sync to debug
rsync -avz ./ deploy@YOUR_SERVER_IP:/opt/eg-chatbot/
```

### Issue: High memory usage

```bash
# Check PM2 memory
pm2 list

# Check Redis memory
redis-cli info memory

# Restart app
pm2 restart eg-chatbot-api

# Clear Redis cache
redis-cli FLUSHDB
```

### Issue: Slow responses

```bash
# Check Ollama
ollama ps

# Check CPU usage
top

# Check logs for slow queries
pm2 logs eg-chatbot-api | grep "Processing:"

# Check Redis latency
redis-cli --latency
```

---

## 📅 STEP 8: Daily Operations

### Morning Checklist

```bash
# SSH to server
ssh deploy@YOUR_SERVER_IP

# Check app status
pm2 status

# Check logs for errors
pm2 logs eg-chatbot-api --lines 50 | grep ERROR

# Check system resources
df -h && free -h

# Check Redis
redis-cli ping
```

### Weekly Maintenance

```bash
# Update system packages
sudo apt-get update && sudo apt-get upgrade -y

# Clear old logs
pm2 flush

# Check Redis memory
redis-cli info memory

# Restart app (during low traffic)
pm2 restart eg-chatbot-api
```

### Monthly Tasks

```bash
# Update Python packages
cd /opt/eg-chatbot
source venv/bin/activate
pip list --outdated
pip install --upgrade <package-name>

# Backup Redis data
redis-cli SAVE
cp /var/lib/redis/dump.rdb /backup/redis-$(date +%Y%m%d).rdb

# Review disk usage
du -sh /opt/eg-chatbot/*
du -sh /var/log/eg-chatbot/*

# Clean old logs
find /var/log/eg-chatbot/ -name "*.log" -mtime +30 -delete
```

---

## 🎯 Quick Reference

### Essential Commands

```bash
# Deployment
git push origin main                    # Trigger CI/CD deployment

# PM2 Management
pm2 status                              # Check status
pm2 logs eg-chatbot-api                # View logs
pm2 restart eg-chatbot-api             # Restart app
pm2 monit                               # Monitor resources

# Server Management
ssh deploy@YOUR_SERVER_IP              # Connect to server
sudo systemctl status redis-server      # Check Redis
ollama list                             # Check Ollama models
curl http://localhost:8000/health       # Health check

# Troubleshooting
pm2 logs eg-chatbot-api --err          # View errors
tail -f /var/log/eg-chatbot/error.log  # Watch error logs
redis-cli ping                          # Test Redis
df -h                                   # Check disk space
```

### Important File Locations

```
Application:     /opt/eg-chatbot/
Logs:            /var/log/eg-chatbot/
Virtual Env:     /opt/eg-chatbot/venv/
PM2 Config:      /opt/eg-chatbot/ecosystem.config.js
Environment:     /opt/eg-chatbot/.env
Nginx Config:    /etc/nginx/sites-available/eg-chatbot
Redis Data:      /var/lib/redis/
```

---

## ✅ Deployment Checklist

Use this checklist for your deployment:

### Server Setup (One-Time)
- [ ] Server created and accessible via SSH
- [ ] Python 3.10+ installed
- [ ] Redis installed and running
- [ ] Ollama installed with model downloaded
- [ ] Node.js and PM2 installed
- [ ] Deploy user created
- [ ] SSH keys generated
- [ ] Application directory created
- [ ] Firewall configured

### GitHub Setup (One-Time)
- [ ] Repository created
- [ ] Code pushed to GitHub
- [ ] GitHub Secrets added (all 4)
- [ ] CI/CD workflow file in `.github/workflows/deploy.yml`

### First Deployment (One-Time)
- [ ] Files copied to server manually
- [ ] `.env` file created on server
- [ ] Dependencies installed
- [ ] PM2 started successfully
- [ ] Health check passes
- [ ] Nginx configured (optional)
- [ ] SSL certificate installed (optional)

### Testing
- [ ] API responds to health check
- [ ] Chat endpoint works
- [ ] PM2 shows app as online
- [ ] Logs show no errors
- [ ] CI/CD deployment works

### Done!
- [ ] Application is live
- [ ] CI/CD is working
- [ ] Monitoring is setup
- [ ] Documentation is complete

---

## 🆘 Get Help

If you're stuck:

1. **Check PM2 logs:**
   ```bash
   pm2 logs eg-chatbot-api --err
   ```

2. **Check GitHub Actions:**
   Go to: Repository → Actions → View logs

3. **Verify all services:**
   ```bash
   pm2 status
   sudo systemctl status redis-server
   ollama list
   sudo systemctl status nginx
   ```

4. **Common issues:**
   - SSH key not working → Regenerate and update GitHub Secret
   - Port 8000 in use → Kill process or change port
   - Redis connection failed → Start Redis
   - Ollama model missing → Pull model again

---

## 🎉 Success!

Your EG Chatbot API is now deployed with:
- ✅ Automated CI/CD (push to deploy)
- ✅ PM2 process management (auto-restart)
- ✅ Production-ready setup
- ✅ Monitoring and logging
- ✅ Scalable architecture

**Next time you want to deploy:**
Just push to GitHub main branch → Done! 🚀

---

**End of Deployment Guide**
