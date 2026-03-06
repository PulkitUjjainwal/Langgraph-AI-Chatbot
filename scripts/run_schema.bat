@echo off
REM Run PostgreSQL Schema Script
REM
REM This script creates all database tables, indexes, and functions
REM

echo ========================================
echo Running PostgreSQL Schema
echo ========================================
echo.

REM Check if Docker container is running
docker ps | findstr chatbot-postgres >nul 2>&1
if errorlevel 1 (
    echo ERROR: PostgreSQL container is not running!
    echo.
    echo Please run setup_postgres_docker.bat first
    echo Or start the container: docker start chatbot-postgres
    echo.
    pause
    exit /b 1
)

echo ✓ PostgreSQL container is running
echo.

REM Check if schema file exists
if not exist "chatbot\database\postgres_schema.sql" (
    echo ERROR: Schema file not found!
    echo Expected location: chatbot\database\postgres_schema.sql
    echo.
    pause
    exit /b 1
)

echo ✓ Schema file found
echo.

REM Run schema
echo Running schema SQL file...
echo This will create:
echo   - Tables: users, refresh_tokens, pages, faq, conversations, messages, embeddings, feedback
echo   - Indexes: Full-text search, vector similarity (HNSW), partitions
echo   - Functions: Triggers, cleanup, partition creation
echo   - Views: Analytics, statistics
echo.

docker exec -i chatbot-postgres psql -U postgres -d chatbot < chatbot\database\postgres_schema.sql

if errorlevel 1 (
    echo.
    echo ERROR: Schema creation failed!
    echo.
    echo This might be normal if tables already exist.
    echo Check the output above for actual errors.
    echo.
) else (
    echo.
    echo ========================================
    echo ✅ Schema Created Successfully!
    echo ========================================
    echo.
)

REM Verify tables
echo Verifying tables...
docker exec chatbot-postgres psql -U postgres -d chatbot -c "\dt"
echo.

REM Check pgvector
echo Verifying pgvector extension...
docker exec chatbot-postgres psql -U postgres -d chatbot -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
echo.

echo ========================================
echo Database Setup Complete!
echo ========================================
echo.
echo You can now:
echo   1. Update your .env file (copy from .env.example)
echo   2. Install Python dependencies: pip install -r requirements.txt
echo   3. Start your application: uvicorn fastapi_chatbot:app --reload
echo.
echo To connect to database:
echo   docker exec -it chatbot-postgres psql -U postgres -d chatbot
echo.
pause
