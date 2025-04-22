from fastapi import FastAPI, Request, HTTPException
from .routers import functions, metrics, config
from .db.session import engine, SessionLocal
from .db import base  # Import all models
from .models import function, settings, user  # Explicitly import all models

# Create database tables
base.Base.metadata.create_all(bind=engine)

# Also create legacy tables
function.Base.metadata.create_all(bind=engine)

# Ensure the platform_settings table exists
def initialize_settings():
    from .models.settings import PlatformSettings
    db = SessionLocal()
    try:
        # Check if platform_settings table exists
        settings = db.query(PlatformSettings).first()
        if settings is None:
            # Create default settings
            default_settings = PlatformSettings(
                enforce_gvisor=True,
                allow_docker_runtime=False,
                allow_unsecured_networks=False,
                allow_custom_containers=False,
                max_concurrent_functions=10,
                default_memory_limit=256,
                default_cpu_limit=0.5,
                default_timeout=300,
                enable_detailed_logging=True,
                retain_execution_logs_days=30
            )
            db.add(default_settings)
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"Warning: Could not initialize platform settings: {e}")
    finally:
        db.close()

# Initialize settings after tables are created
initialize_settings()

from .execution.engine import ExecutionEngine
from .execution.gvisor_engine import GVisorEngine
from .execution.cli_engine import CLIEngine
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

    # Initialize CLI engine (which may use gVisor if available)
    try:
        app.state.cli_engine = CLIEngine()
        gvisor_status = getattr(app.state.cli_engine, 'verified_gvisor', False)
        if gvisor_status:
            logger.info("CLI+gVisor engine initialized successfully with verified gVisor security")
        else:
            logger.warning("CLI engine initialized WITHOUT gVisor security!")
    except Exception as e:
        logger.error(f"Failed to initialize CLI engine: {str(e)}")
        app.state.cli_engine = None

    # Check if dedicated gVisor engine is available
    gvisor_available = check_gvisor_availability()

    if gvisor_available:
        try:
            # Initialize gVisor engine with is_wsl=False for native Linux
            app.state.gvisor_engine = GVisorEngine(is_wsl=False)
            logger.info("gVisor engine initialized and tested successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize gVisor engine: {str(e)}")
            logger.warning("SECURITY NOTICE: gVisor engine will not be available as gVisor security cannot be guaranteed")
            app.state.gvisor_engine = None
            gvisor_available = False
    else:
        logger.warning("gVisor not available, falling back to Docker engine")
        app.state.gvisor_engine = None
        gvisor_available = False

    # Store gVisor availability in app state
    app.state.gvisor_available = gvisor_available or (hasattr(app.state, 'cli_engine') and 
                                                     getattr(app.state.cli_engine, 'verified_gvisor', False))
    
    # Security check - ensure at least one secure runtime is available
    has_secure_cli = hasattr(app.state, 'cli_engine') and getattr(app.state.cli_engine, 'verified_gvisor', False)
    has_secure_gvisor = hasattr(app.state, 'gvisor_engine') and app.state.gvisor_engine is not None
    
    if not has_secure_cli and not has_secure_gvisor:
        logger.error("SECURITY WARNING: No secure runtime (gVisor) is available. System security cannot be guaranteed.")
        app.state.secure_runtime_available = False
        app.state.security_warning = "No secure runtime (gVisor) is available. System security cannot be guaranteed."
    else:
        app.state.secure_runtime_available = True
        app.state.security_warning = None

except Exception as e:
    logger.error(f"Failed to initialize execution engines: {str(e)}")
    raise HTTPException(status_code=500, detail="Failed to initialize execution engines")

# Include routers
app.include_router(functions.router)
app.include_router(metrics.router)
app.include_router(config.router)

@app.middleware("http")
async def execution_engine_middleware(request: Request, call_next):
    # Initialize execution engines
    logger.info("Initializing execution engines")
    
    # Initialize CLI engine with gVisor support
    cli_engine = CLIEngine()
    request.state.cli_engine = cli_engine
    
    # Check if gVisor is verified in the CLI engine
    if hasattr(cli_engine, 'verified_gvisor') and cli_engine.verified_gvisor:
        logger.info("CLI engine has verified gVisor support")
    else:
        logger.warning("CLI engine does not have verified gVisor support")
    
    # Initialize dedicated gVisor engine if available
    try:
        gvisor_engine = GVisorEngine()
        request.state.gvisor_engine = gvisor_engine
        logger.info("GVisor engine initialized")
    except Exception as e:
        logger.warning(f"GVisor engine initialization failed: {str(e)}")
        request.state.gvisor_engine = None
    
    # Initialize Docker engine for legacy support
    try:
        docker_engine = ExecutionEngine()
        request.state.docker_engine = docker_engine
        logger.info("Docker engine initialized")
    except Exception as e:
        logger.warning(f"Docker engine initialization failed: {str(e)}")
        request.state.docker_engine = None
    
    response = await call_next(request)
    return response

@app.get("/")
async def root():
    security_status = "secure" if getattr(app.state, "secure_runtime_available", False) else "insecure"
    security_warning = getattr(app.state, "security_warning", None)
    
    # Collect all available runtimes
    available_runtimes = []
    
    # Always add docker
    available_runtimes.append("docker")
    
    # Add cli/cli+gvisor
    if hasattr(app.state, 'cli_engine') and app.state.cli_engine is not None:
        if getattr(app.state.cli_engine, 'verified_gvisor', False):
            available_runtimes.append("cli+gvisor")
        else:
            available_runtimes.append("cli")
    
    # Add gVisor if available
    if app.state.gvisor_available:
        available_runtimes.append("gvisor")
    
    # Build runtime status information
    runtime_status = {
        "docker": "available"
    }
    
    if hasattr(app.state, 'cli_engine') and app.state.cli_engine is not None:
        if getattr(app.state.cli_engine, 'verified_gvisor', False):
            runtime_status["cli+gvisor"] = "available (secured with gVisor)"
        else:
            runtime_status["cli"] = "available (without gVisor security)"
    else:
        runtime_status["cli"] = "unavailable"
        runtime_status["cli+gvisor"] = "unavailable"
    
    runtime_status["gvisor"] = "available" if app.state.gvisor_available else "unavailable"
    
    response = {
        "message": "Welcome to the Serverless Function Platform API",
        "version": "1.0.0",
        "platform": "Linux",
        "security_status": security_status,
        "features": [
            "Docker-based function execution",
            "gVisor-based function execution (if available)",
            "CLI+gVisor-based function execution",
            "Function warm-up mechanism",
            "Container pooling",
            "Metrics collection",
            "Error handling",
            "Strict security verification"
        ],
        "available_runtimes": available_runtimes,
        "runtime_status": runtime_status
    }
    
    if security_warning:
        response["security_warning"] = security_warning
        
    return response 
