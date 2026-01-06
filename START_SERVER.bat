@echo off
REM ============================================================================
REM MI Chat Bot Server Startup Script (UTF-8 Encoding Fix)
REM ============================================================================

echo Starting MI Chat Bot Server...
echo.

REM Set UTF-8 encoding for Python to fix Unicode character errors
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Start the FastAPI server
echo [INFO] Starting FastAPI server on port 8000...
echo [INFO] API Docs: http://localhost:8000/docs
echo [INFO] Health Check: http://localhost:8000/api/health
echo.
echo Press Ctrl+C to stop the server
echo.

python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --reload

pause
