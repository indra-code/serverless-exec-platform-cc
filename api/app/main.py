from fastapi import FastAPI, Request, HTTPException
from .routers import functions, metrics
from .database.database import engine
from .models import function
from .execution.engine import ExecutionEngine
from .execution.gvisor_engine import GVisorEngine
from .execution.cli_engine import CLIExecutionEngine
from .metrics.collector import MetricsCollector
import logging
import os
import subprocess
import platform
import sys
import docker
from .patches import docker_patch  # Fix Docker credential store issues


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create database tables
function.Base.metadata.create_all(bind=engine)

# Initialize the metrics table
try:
    from .models.metrics import ExecutionMetric  # Import the model
    # This will create the table if it doesn't exist
    ExecutionMetric.__table__.create(bind=engine, checkfirst=True)
    logger.info("Metrics table initialized successfully")
    
    # Run the metrics table migration to ensure indexes
    try:
        from .database.create_metrics_table import run_migration
        run_migration()
        logger.info("Metrics table migration completed")
    except Exception as e:
        logger.warning(f"Metrics table migration warning (non-critical): {str(e)}")
except Exception as e:
    logger.warning(f"Failed to initialize metrics table (non-critical): {str(e)}")

app = FastAPI(
    title="Serverless Function Platform API",
    description="API for managing serverless functions with multiple virtualization technologies",
    version="1.0.0"
)


def get_docker_client():
    """Get Docker client based on environment"""
    try:
        # First try to connect to Docker Desktop for Windows
        client = docker.from_env()
        client.ping()
        logger.info("Connected to Docker Desktop for Windows")
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Docker Desktop: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to connect to Docker Desktop. Please make sure Docker Desktop is running."
        )

def check_gvisor_availability():
    """Check gVisor availability based on the platform"""
    try:
            # Native Linux checks
        logger.info("Running on native Linux, checking for gVisor...")

            # Check if gVisor is installed
        result = subprocess.run(['which', 'runsc'], capture_output=True, text=True)
        if result.returncode != 0:
                logger.warning("gVisor (runsc) not found on native Linux")
                return False

            # Check if Docker is configured to use gVisor
        result = subprocess.run(['docker', 'info'], capture_output=True, text=True)
        if 'runsc' not in result.stdout:
                logger.warning("Docker not configured to use gVisor runtime on native Linux")
                return False

            # Test gVisor with a simple container
        result = subprocess.run(['docker', 'run', '--runtime=runsc', 'hello-world'], 
                             capture_output=True, text=True)
        if result.returncode != 0:
                logger.warning("gVisor test failed on native Linux")
                return False

        logger.info("gVisor is available and working on native Linux")
        return True

    except Exception as e:
        logger.warning(f"Error checking for gVisor: {str(e)}")
        return False

# Initialize execution engines and metrics collector
try:
    # Initialize Docker engine
    docker_client = get_docker_client()
    app.state.docker_engine = ExecutionEngine(docker_client=docker_client)
    logger.info("Docker engine initialized successfully")

    # Initialize CLI engine (for direct use of run_function.py)
    try:
        app.state.cli_engine = CLIExecutionEngine()
        logger.info("CLI engine initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize CLI engine: {str(e)}")
        app.state.cli_engine = None

    # Check if gVisor is available
    gvisor_available = check_gvisor_availability()

    if gvisor_available:
        try:
            # Initialize gVisor engine with is_wsl=False for native Linux
            app.state.gvisor_engine = GVisorEngine(is_wsl=False)
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
    # Add CLI engine to request state
    if hasattr(app.state, 'cli_engine'):
        request.state.cli_engine = app.state.cli_engine
    else:
        request.state.cli_engine = None
    # Check if gvisor_engine exists in app.state before assigning
    if hasattr(app.state, 'gvisor_engine'):
            request.state.gvisor_engine = app.state.gvisor_engine
    else:
        request.state.gvisor_engine = None
    response = await call_next(request)
    return response

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Serverless Function Platform API",
        "version": "1.0.0",
        "platform": "Linux",
        "features": [
            "Docker-based function execution",
            "gVisor-based function execution (if available)",
            "CLI-based function execution",
            "Function warm-up mechanism",
            "Container pooling",
            "Metrics collection",
            "Error handling"
        ],
        "available_runtimes": [
            "docker",
            "gvisor" if app.state.gvisor_available else None,
            "cli"
        ],
        "status": {
            "docker": "available",
            "gvisor": "available" if app.state.gvisor_available else "unavailable",
            "cli": "available" if hasattr(app.state, 'cli_engine') and app.state.cli_engine is not None else "unavailable"
        }
    } 
