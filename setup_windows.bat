@echo off
echo Setting up Serverless Function Platform for Windows...

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Please install Python 3.10 or later from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check if Docker is installed
docker --version >nul 2>&1
if errorlevel 1 (
    echo Docker is not installed. Please install Docker Desktop for Windows from https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

:: Create virtual environment
echo Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat

:: Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
pip install docker fastapi uvicorn sqlalchemy psycopg2-binary python-dotenv

:: Create necessary directories
echo Creating directories...
if not exist uploads mkdir uploads
if not exist logs mkdir logs

:: Create .env file
echo Creating .env file...
(
echo POSTGRES_USER=postgres
echo POSTGRES_PASSWORD=postgres
echo POSTGRES_SERVER=localhost
echo POSTGRES_PORT=5432
echo POSTGRES_DB=function_db
) > .env

:: Start Docker containers
echo Starting Docker containers...
docker run -d --name redis-server -p 6379:6379 redis
docker run -d --name postgres-server -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=function_db -p 5432:5432 postgres:latest

:: Wait for containers to start
echo Waiting for containers to start...
timeout /t 10

:: Create test function
echo Creating test function...
(
echo def handler():
echo     print("Hello, World!")
echo     return {"message": "Hello, World!"}
echo 
echo if __name__ == "__main__":
echo     handler()
) > uploads\handler.py

echo Setup complete!
echo.
echo To start the server, run:
echo call venv\Scripts\activate.bat
echo cd api
echo uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
echo.
echo The API will be available at http://localhost:8000
pause 