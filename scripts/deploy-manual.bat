@echo off
REM Manual Deployment Script for EG Chatbot (Windows)
REM Run this from the project root directory

REM ============================================================
REM CONFIGURATION - UPDATE THESE VALUES
REM ============================================================
SET SERVER_USER=deploy
SET SERVER_IP=YOUR_SERVER_IP
SET DEPLOY_PATH=/opt/eg-chatbot

echo ============================================================
echo EG Chatbot Manual Deployment
echo ============================================================
echo.

REM ============================================================
REM STEP 1: Build Frontend Widget
REM ============================================================
echo [1/4] Building frontend widget...
cd frontend
call npm install
call npm run build
cd ..
echo Done!
echo.

REM ============================================================
REM STEP 2: Copy Files to Server using SCP
REM ============================================================
echo [2/4] Copying files to server...
echo This will copy all project files (excluding .git, venv, etc.)
echo.

REM Using SCP (slower but works on Windows)
scp -r fastapi_chatbot.py %SERVER_USER%@%SERVER_IP%:%DEPLOY_PATH%/
scp -r requirements.txt %SERVER_USER%@%SERVER_IP%:%DEPLOY_PATH%/
scp -r ecosystem.config.js %SERVER_USER%@%SERVER_IP%:%DEPLOY_PATH%/
scp -r chatbot %SERVER_USER%@%SERVER_IP%:%DEPLOY_PATH%/
scp -r data %SERVER_USER%@%SERVER_IP%:%DEPLOY_PATH%/
scp -r backend\assets\chat-widget.js %SERVER_USER%@%SERVER_IP%:%DEPLOY_PATH%/widget-dist/

echo Files copied!
echo.

REM ============================================================
REM STEP 3: Run Server Commands
REM ============================================================
echo [3/4] Running deployment commands on server...
echo.

ssh %SERVER_USER%@%SERVER_IP% "cd %DEPLOY_PATH% && source venv/bin/activate && pip install -r requirements.txt && pm2 reload ecosystem.config.js && pm2 save && pm2 status"

echo.

REM ============================================================
REM STEP 4: Health Check
REM ============================================================
echo [4/4] Running health check...
timeout /t 10 /nobreak > nul
curl http://%SERVER_IP%:8000/api/health

echo.
echo ============================================================
echo DEPLOYMENT COMPLETE!
echo ============================================================
echo API URL:    http://%SERVER_IP%/api/health
echo Widget URL: http://%SERVER_IP%/chat-widget.js
echo ============================================================

pause
