import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Database connection settings
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "metanoid323")
POSTGRES_SERVER = os.getenv("POSTGRES_SERVER", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "function_db")

SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"

logger.info(f"Testing database connection to {POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}")

try:
    # Create engine
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    
    # Test connection
    with engine.connect() as conn:
        logger.info("Successfully connected to the database")
        
        # Check if the functions table exists
        result = conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'functions')"))
        table_exists = result.scalar()
        
        if table_exists:
            logger.info("Functions table exists")
            
            # Get table schema
            result = conn.execute(text("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'functions'"))
            columns = result.fetchall()
            
            logger.info("Table schema:")
            for column in columns:
                logger.info(f"  {column[0]}: {column[1]} (nullable: {column[2]})")
        else:
            logger.warning("Functions table does not exist")
            
            # Create the table
            logger.info("Creating functions table...")
            conn.execute(text("""
                CREATE TABLE functions (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR UNIQUE NOT NULL,
                    description TEXT,
                    code_path VARCHAR NOT NULL,
                    runtime VARCHAR DEFAULT 'python',
                    timeout INTEGER DEFAULT 30,
                    memory INTEGER DEFAULT 128,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE
                )
            """))
            conn.commit()
            logger.info("Functions table created successfully")
            
except Exception as e:
    logger.error(f"Error: {str(e)}")
    sys.exit(1) 