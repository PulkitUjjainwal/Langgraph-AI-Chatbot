// PM2 Ecosystem Configuration for Export Genius Chat Bot API
// Learn more: https://pm2.keymetrics.io/docs/usage/application-declaration/

module.exports = {
  apps: [
    {
      // Application name
      name: 'eg-chatbot-api',

      // Python script to run
      script: '/opt/eg-chatbot/venv/bin/uvicorn',

      // Arguments passed to script
      args: 'fastapi_chatbot:app --host 0.0.0.0 --port 8000 --workers 4',

      // Working directory
      cwd: '/opt/eg-chatbot',

      // Interpreter (use Python from venv)
      interpreter: '/opt/eg-chatbot/venv/bin/python3',

      // Instances (set to 1 when using uvicorn workers)
      instances: 1,

      // Execution mode
      exec_mode: 'fork',

      // Auto-restart configuration
      autorestart: true,
      watch: false, // Set to true for development
      max_memory_restart: '2G',

      // Environment variables
      env: {
        NODE_ENV: 'production',
        REDIS_HOST: 'localhost',
        REDIS_PORT: 6379,
        REDIS_DB: 0,
        LLM_MODEL: 'deepseek-v3.1:671b-cloud',
        OLLAMA_BASE_URL: 'http://localhost:11434',
      },

      // Logging
      error_file: '/var/log/eg-chatbot/error.log',
      out_file: '/var/log/eg-chatbot/out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,

      // Restart delay
      restart_delay: 4000,

      // Max restarts within time window
      max_restarts: 10,
      min_uptime: '10s',

      // Graceful shutdown
      kill_timeout: 5000,
      wait_ready: true,
      listen_timeout: 10000,

      // Post-deploy actions
      post_update: ['pip install -r requirements.txt'],
    },
  ],

  // Deployment configuration
  deploy: {
    production: {
      user: 'deploy', // SSH user
      host: ['your-server-ip'], // Replace with your server IP
      ref: 'origin/main', // Git branch
      repo: 'git@github.com:yourusername/eg-chatbot.git', // Replace with your repo
      path: '/opt/eg-chatbot',
      'post-deploy':
        'source venv/bin/activate && pip install -r requirements.txt && pm2 reload ecosystem.config.js --env production',
      'pre-deploy-local': 'echo "Deploying to production server..."',
      'post-deploy-local': 'echo "Deployment complete!"',
    },
  },
};
