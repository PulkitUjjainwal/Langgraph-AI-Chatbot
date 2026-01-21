#!/bin/bash
# Manual Deployment Script for EG Chatbot
# Run this on your LOCAL machine to deploy to server

# ============================================================
# CONFIGURATION - UPDATE THESE VALUES
# ============================================================
SERVER_USER="deploy"
SERVER_IP="YOUR_SERVER_IP"  # Change this!
DEPLOY_PATH="/opt/eg-chatbot"
LOCAL_PATH="."  # Current directory

# ============================================================
# PRE-DEPLOYMENT: Build Frontend Widget
# ============================================================
echo "🔨 Building frontend widget..."
cd frontend
npm install
npm run build
cd ..
echo "✅ Widget built"

# ============================================================
# DEPLOYMENT: Sync Files to Server
# ============================================================
echo "📤 Syncing files to server..."
rsync -avz --delete \
    --exclude '.git' \
    --exclude '.github' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'venv' \
    --exclude '.env' \
    --exclude 'test_*.py' \
    --exclude 'frontend/node_modules' \
    "$LOCAL_PATH/" "$SERVER_USER@$SERVER_IP:$DEPLOY_PATH/"

echo "✅ Files synced"

# ============================================================
# POST-DEPLOYMENT: Run Commands on Server
# ============================================================
echo "🔧 Running post-deployment commands..."
ssh "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
cd /opt/eg-chatbot

echo "📦 Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "📁 Setting up widget..."
mkdir -p widget-dist
cp backend/assets/chat-widget.js widget-dist/

echo "🔄 Reloading PM2..."
pm2 reload ecosystem.config.js --env production
pm2 save

echo "✅ Deployment complete!"
pm2 status
ENDSSH

# ============================================================
# HEALTH CHECK
# ============================================================
echo "🏥 Running health check..."
sleep 10
curl --fail "http://$SERVER_IP:8000/api/health" && echo "✅ API healthy!" || echo "❌ API health check failed"

echo ""
echo "================================================"
echo "🎉 DEPLOYMENT COMPLETE"
echo "================================================"
echo "API URL:    http://$SERVER_IP:8000"
echo "Widget URL: http://$SERVER_IP/chat-widget.js"
echo "Health:     http://$SERVER_IP/api/health"
echo "================================================"
