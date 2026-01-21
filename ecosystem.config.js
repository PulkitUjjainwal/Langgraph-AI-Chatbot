// PM2 Ecosystem Configuration for Market Inside Chat Bot
// Includes: Backend API + Frontend Widget Server
// Learn more: https://pm2.keymetrics.io/docs/usage/application-declaration/

module.exports = {
  apps: [
    // ============================================================
    // BACKEND API - FastAPI Chatbot (Market Inside)
    // ============================================================
    // IMPORTANT: Using 2 workers to prevent memory issues
    // Each worker loads FAISS index + embeddings (~3-4GB each)
    // 4 workers = 12-16GB RAM usage (causes 98% memory on 16GB server)
    // 2 workers = 6-8GB RAM usage (safe for 16GB server)
    {
      name: 'mi-chatbot-api',
      script: '/opt/mi-chatbot/venv/bin/uvicorn',
      args: 'fastapi_chatbot:app --host 0.0.0.0 --port 8000 --workers 2',
      cwd: '/opt/mi-chatbot',
      interpreter: '/opt/mi-chatbot/venv/bin/python3',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      watch: false,
      max_memory_restart: '4G',  // Restart if single process exceeds 4GB

      // Environment variables
      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',  // Ensure logs are flushed immediately
      },

      // Logging
      error_file: '/var/log/mi-chatbot/api-error.log',
      out_file: '/var/log/mi-chatbot/api-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,

      // Restart settings
      restart_delay: 4000,
      max_restarts: 10,
      min_uptime: '10s',
      kill_timeout: 5000,
      wait_ready: true,
      listen_timeout: 10000,
    },

    // ============================================================
    // NOTE: Widget is served via Nginx as static file
    // No need for separate PM2 process - saves ~512MB RAM
    // Nginx config serves: /opt/mi-chatbot/widget-dist/chat-widget.js
    // ============================================================
  ],

  // Deployment configuration
  deploy: {
    production: {
      user: 'deploy',
      host: ['chatbot.marketinsidedata.com'],
      ref: 'origin/main',
      repo: 'https://github.com/Export-genius/MI-Chatbot_API.git',
      path: '/opt/mi-chatbot',
      'pre-deploy-local': 'echo "Deploying to Market Inside production server..."',
      'post-deploy':
        'source venv/bin/activate && pip install -r requirements.txt && cd frontend && npm install && npm run build && mkdir -p ../widget-dist && cp ../backend/assets/chat-widget.js ../widget-dist/ && pm2 reload ecosystem.config.js --env production',
      'post-deploy-local': 'echo "Deployment complete!"',
    },
  },
};
