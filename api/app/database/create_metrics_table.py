import logging
from sqlalchemy import text
from .database import engine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    logger.info("Starting database migration to create metrics table")
    
    try:
        # Connect to the database
        with engine.connect() as conn:
            # Check if table exists
            logger.info("Checking if execution_metrics table exists")
            result = conn.execute(text("SELECT to_regclass('execution_metrics')"))
            table_exists = result.scalar() is not None
            
            if not table_exists:
                logger.info("Creating execution_metrics table")
                
                # Create the table
                conn.execute(text("""
                CREATE TABLE execution_metrics (
                    id SERIAL PRIMARY KEY,
                    function_id INTEGER NOT NULL REFERENCES functions(id) ON DELETE CASCADE,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    execution_time FLOAT NOT NULL,
                    memory_used FLOAT,
                    success BOOLEAN DEFAULT TRUE,
                    error VARCHAR,
                    runtime VARCHAR NOT NULL,
                    resource_usage JSONB,
                    request_data JSONB
                )
                """))
                
                # Create indexes
                conn.execute(text("CREATE INDEX idx_execution_metrics_function_id ON execution_metrics(function_id)"))
                conn.execute(text("CREATE INDEX idx_execution_metrics_timestamp ON execution_metrics(timestamp)"))
                
                conn.commit()
                logger.info("Successfully created execution_metrics table and indexes")
            else:
                logger.info("execution_metrics table already exists, skipping creation")
        
        logger.info("Migration completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error during migration: {str(e)}")
        return False

if __name__ == "__main__":
    run_migration() 