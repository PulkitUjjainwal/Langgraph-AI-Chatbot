@echo off
REM PostgreSQL + pgvector Setup Script (Docker)
REM
REM This script sets up PostgreSQL with pgvector extension using Docker
REM

echo ========================================
echo PostgreSQL + pgvector Setup (Docker)
echo ========================================
echo.

REM Check if Docker is installed
docker --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not installed!
    echo.
    echo Please install Docker Desktop from:
    echo https://www.docker.com/products/docker-desktop
    echo.
    pause
    exit /b 1
)

echo ✓ Docker is installed
echo.

REM Stop and remove existing container (if any)
echo Removing existing PostgreSQL container (if exists)...
docker stop chatbot-postgres >nul 2>&1
docker rm chatbot-postgres >nul 2>&1
echo.

REM Pull latest pgvector image
echo Pulling PostgreSQL + pgvector image...
docker pull ankane/pgvector:latest
echo.

REM Start PostgreSQL container
echo Starting PostgreSQL container...
docker run -d ^
  --name chatbot-postgres ^
  -e POSTGRES_PASSWORD=chatbot_password_123 ^
  -e POSTGRES_DB=chatbot ^
  -e POSTGRES_USER=postgres ^
  -p 5432:5432 ^
  -v postgres_data:/var/lib/postgresql/data ^
  ankane/pgvector:latest

if errorlevel 1 (
    echo ERROR: Failed to start PostgreSQL container
    pause
    exit /b 1
)

echo ✓ PostgreSQL container started successfully
echo.

REM Wait for PostgreSQL to be ready
echo Waiting for PostgreSQL to be ready...
timeout /t 10 /nobreak >nul

REM Test connection
echo Testing PostgreSQL connection...
docker exec chatbot-postgres psql -U postgres -c "SELECT version();" >nul 2>&1
if errorlevel 1 (
    echo WARNING: PostgreSQL might not be ready yet. Wait 10 more seconds...
    timeout /t 10 /nobreak >nul
)

REM Create pgvector extension
echo Creating pgvector extension...
docker exec chatbot-postgres psql -U postgres -d chatbot -c "CREATE EXTENSION IF NOT EXISTS vector;"

if errorlevel 1 (
    echo ERROR: Failed to create pgvector extension
    pause
    exit /b 1
)

echo ✓ pgvector extension created
echo.

REM Verify installation
echo Verifying installation...
docker exec chatbot-postgres psql -U postgres -d chatbot -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
echo.

echo ========================================
echo ✅ PostgreSQL Setup Complete!
echo ========================================
echo.
echo Connection Details:
echo   Host:     localhost
echo   Port:     5432
echo   Database: chatbot
echo   User:     postgres
echo   Password: chatbot_password_123
echo.
echo Container Name: chatbot-postgres
echo.
echo Useful Commands:
echo   - View logs:    docker logs chatbot-postgres
echo   - Stop:         docker stop chatbot-postgres
echo   - Start:        docker start chatbot-postgres
echo   - Remove:       docker rm -f chatbot-postgres
echo   - Connect:      docker exec -it chatbot-postgres psql -U postgres -d chatbot
echo.
echo Next Steps:
echo   1. Update your .env file with the connection details above
echo   2. Run: docker exec -i chatbot-postgres psql -U postgres -d chatbot ^< chatbot\database\postgres_schema.sql
echo   3. Start your application: uvicorn fastapi_chatbot:app --reload
echo.
pause
