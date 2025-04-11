from fastapi import FastAPI, Request, HTTPException
from .routers import functions, metrics
from .database.database import engine
from .models import function
from .execution.engine import ExecutionEngine
from .execution.gvisor_engine import GVisorEngine
from .metrics.collector import MetricsCollector
import logging
import os
import subprocess
import platform
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create database tables
function.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Serverless Function Platform API",
    description="API for managing serverless functions with multiple virtualization technologies",
    version="1.0.0"
)

def is_wsl():
    """Check if running in WSL"""
    if 'microsoft' in platform.uname().release.lower():
        return True
    if os.path.exists('/proc/version'):
        with open('/proc/version', 'r') as f:
            return 'microsoft' in f.read().lower()
    return False

def check_gvisor_availability():
    """Check gVisor availability based on the platform"""
    if is_wsl():
        try:
            result = subprocess.run(['wsl', '-e', 'bash', '-c', 'which runsc'], 
                                 capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"Error checking for gVisor in WSL: {str(e)}")
            return False
    else:
        try:
            result = subprocess.run(['which', 'runsc'], 
                                 capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"Error checking for gVisor: {str(e)}")
            return False

# Initialize execution engines and metrics collector
try:
    # Initialize Docker engine
    app.state.docker_engine = ExecutionEngine()
    logger.info("Docker engine initialized successfully")

    # Check if gVisor is available
    gvisor_available = check_gvisor_availability()
    app.state.is_wsl = is_wsl()

    if gvisor_available:
        try:
            app.state.gvisor_engine = GVisorEngine(is_wsl=app.state.is_wsl)
            # Test gVisor with a simple container
            app.state.gvisor_engine.execute_function("test", "print('Hello, gVisor!')", "python3")
            logger.info("gVisor engine initialized and tested successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize gVisor engine: {str(e)}")
            app.state.gvisor_engine = None
            gvisor_available = False
    else:
        logger.warning("gVisor not available, falling back to Docker engine")
        app.state.gvisor_engine = None
        gvisor_available = False

    # Store gVisor availability in app state
    app.state.gvisor_available = gvisor_available

except Exception as e:
    logger.error(f"Failed to initialize execution engines: {str(e)}")
    raise HTTPException(status_code=500, detail="Failed to initialize execution engines")

# Include routers
app.include_router(functions.router)
app.include_router(metrics.router)

@app.middleware("http")
async def add_execution_engine(request: Request, call_next):
    # Add execution engines to request state
    request.state.docker_engine = app.state.docker_engine
    request.state.gvisor_engine = app.state.gvisor_engine
    response = await call_next(request)
    return response

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Serverless Function Platform API",
        "version": "1.0.0",
        "platform": "WSL" if app.state.is_wsl else "Linux",
        "features": [
            "Docker-based function execution",
            "gVisor-based function execution (if available)",
            "Function warm-up mechanism",
            "Container pooling",
            "Metrics collection",
            "Error handling"
        ],
        "available_runtimes": [
            "docker",
            "gvisor" if app.state.gvisor_available else None
        ],
        "status": {
            "docker": "available",
            "gvisor": "available" if app.state.gvisor_available else "unavailable"
        }
    } 