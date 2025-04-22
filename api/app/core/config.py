import os
from typing import Any, Dict, List, Optional, Union
from dotenv import load_dotenv

from pydantic import validator
from pydantic_settings import BaseSettings

# Load environment variables from .env file
load_dotenv()

# Get database config from environment
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_SERVER = os.getenv("POSTGRES_SERVER", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "function_db")

# Build PostgreSQL URI if possible, otherwise use SQLite
try:
    DB_URI = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"
except:
    DB_URI = "sqlite:///./app.db"

class Settings(BaseSettings):
    """
    Application settings for the serverless execution platform.
    """
    # API settings
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "Serverless Execution Platform"
    
    # Authentication settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey123forsecuritywithgvisor")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Database settings
    SQLALCHEMY_DATABASE_URI: str = os.getenv("DATABASE_URL", DB_URI)
    
    # gVisor security settings
    GVISOR_ENABLED: bool = True
    GVISOR_PATH: str = os.getenv("GVISOR_PATH", "/usr/local/bin/runsc")
    
    # Kubernetes settings
    KUBE_CONFIG_PATH: Optional[str] = os.getenv("KUBE_CONFIG_PATH")
    
    # Docker settings
    DOCKER_HOST: Optional[str] = os.getenv("DOCKER_HOST")
    DOCKER_TLS_VERIFY: bool = os.getenv("DOCKER_TLS_VERIFY", "0") == "1"
    DOCKER_CERT_PATH: Optional[str] = os.getenv("DOCKER_CERT_PATH")
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create global settings object
settings = Settings() 