@echo off
echo ======================================================================
echo Starting Market Inside Data Chatbot
echo ======================================================================
echo.

cd "C:\MI Ticket\MI Chat Bot\Scrapper Function"

REM FIX: Set UTF-8 encoding to prevent Unicode character errors
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

REM Set environment variables for Market Inside
set SITE_ID=marketinside
set SITE_NAME=Market Inside Data
set KB_CHUNKS_FILE=data/kb_marketinside_chunks.json
set FAISS_INDEX_FILE=data/faiss_marketinside_normalized.index
set REDIS_DB=2
set API_PORT=8003

echo Site: Market Inside Data
echo Port: 8003
echo KB: %FAISS_INDEX_FILE%
echo Encoding: UTF-8 (Unicode support enabled)
echo.

REM Start server
echo Starting server on http://localhost:8003
echo API Docs: http://localhost:8003/docs
echo Press Ctrl+C to stop
echo.
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8003 --reload

pause
