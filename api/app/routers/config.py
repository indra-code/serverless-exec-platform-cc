from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.settings import PlatformSettings
from ..core.security import get_temp_admin_user  # Use temporary admin for dev

router = APIRouter(
    prefix="/config",
    tags=["config"],
    dependencies=[Depends(get_temp_admin_user)]  # Only admin users can access these endpoints
)

# Models for configuration endpoints
class SecurityConfig(BaseModel):
    enforce_gvisor: bool = True
    allow_docker_runtime: bool = False
    allow_unsecured_networks: bool = False
    allow_custom_containers: bool = False

class SystemConfig(BaseModel):
    max_concurrent_functions: int = 10
    default_memory_limit: int = 256  # MB
    default_cpu_limit: float = 0.5   # CPU cores
    default_timeout: int = 300       # seconds

# Get current security configuration
@router.get("/security", response_model=SecurityConfig)
async def get_security_config(db: Session = Depends(get_db)):
    """
    Get current platform security configuration.
    Only accessible to platform admins.
    """
    settings = db.query(PlatformSettings).first()
    
    if not settings:
        # Create default settings if none exist
        settings = PlatformSettings(
            enforce_gvisor=True,
            allow_docker_runtime=False,
            allow_unsecured_networks=False,
            allow_custom_containers=False
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return SecurityConfig(
        enforce_gvisor=settings.enforce_gvisor,
        allow_docker_runtime=settings.allow_docker_runtime,
        allow_unsecured_networks=settings.allow_unsecured_networks,
        allow_custom_containers=settings.allow_custom_containers
    )

# Update security configuration
@router.put("/security", response_model=SecurityConfig)
async def update_security_config(config: SecurityConfig, db: Session = Depends(get_db)):
    """
    Update platform security configuration.
    Only accessible to platform admins.
    """
    settings = db.query(PlatformSettings).first()
    
    if not settings:
        settings = PlatformSettings()
        db.add(settings)
    
    # Update settings
    settings.enforce_gvisor = config.enforce_gvisor
    settings.allow_docker_runtime = config.allow_docker_runtime
    settings.allow_unsecured_networks = config.allow_unsecured_networks
    settings.allow_custom_containers = config.allow_custom_containers
    
    # Additional validation
    if settings.enforce_gvisor and settings.allow_docker_runtime:
        # This is a contradictory setting, since Docker can't enforce gVisor
        # Prioritize security by turning off Docker
        settings.allow_docker_runtime = False
    
    db.commit()
    db.refresh(settings)
    
    return SecurityConfig(
        enforce_gvisor=settings.enforce_gvisor,
        allow_docker_runtime=settings.allow_docker_runtime,
        allow_unsecured_networks=settings.allow_unsecured_networks,
        allow_custom_containers=settings.allow_custom_containers
    )

# Get system configuration
@router.get("/system", response_model=SystemConfig)
async def get_system_config(db: Session = Depends(get_db)):
    """
    Get current system resource configuration.
    Only accessible to platform admins.
    """
    settings = db.query(PlatformSettings).first()
    
    if not settings:
        # Create default settings if none exist
        settings = PlatformSettings(
            max_concurrent_functions=10,
            default_memory_limit=256,
            default_cpu_limit=0.5,
            default_timeout=300
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return SystemConfig(
        max_concurrent_functions=settings.max_concurrent_functions,
        default_memory_limit=settings.default_memory_limit,
        default_cpu_limit=settings.default_cpu_limit,
        default_timeout=settings.default_timeout
    )

# Update system configuration
@router.put("/system", response_model=SystemConfig)
async def update_system_config(config: SystemConfig, db: Session = Depends(get_db)):
    """
    Update system resource configuration.
    Only accessible to platform admins.
    """
    settings = db.query(PlatformSettings).first()
    
    if not settings:
        settings = PlatformSettings()
        db.add(settings)
    
    # Update settings
    settings.max_concurrent_functions = config.max_concurrent_functions
    settings.default_memory_limit = config.default_memory_limit
    settings.default_cpu_limit = config.default_cpu_limit
    settings.default_timeout = config.default_timeout
    
    db.commit()
    db.refresh(settings)
    
    return SystemConfig(
        max_concurrent_functions=settings.max_concurrent_functions,
        default_memory_limit=settings.default_memory_limit,
        default_cpu_limit=settings.default_cpu_limit,
        default_timeout=settings.default_timeout
    ) 