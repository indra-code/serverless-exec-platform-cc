from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging

from ..core.config import settings

# Setup logging
logger = logging.getLogger(__name__)

# Create the SQLAlchemy engine with better connection parameters
try:
    engine = create_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={
            "connect_timeout": 10,
            "application_name": "serverless_platform"
        } if "postgresql" in settings.SQLALCHEMY_DATABASE_URI else {}
    )
    
    # Test the connection
    with engine.connect() as conn:
        logger.info(f"Successfully connected to database: {settings.SQLALCHEMY_DATABASE_URI}")
except Exception as e:
    logger.error(f"Database connection error: {str(e)}")
    # Fallback to SQLite if PostgreSQL connection fails
    fallback_uri = "sqlite:///./app.db"
    logger.info(f"Falling back to SQLite: {fallback_uri}")
    engine = create_engine(fallback_uri, connect_args={"check_same_thread": False})

# Create a SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get a DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
    finally:
        db.close() 