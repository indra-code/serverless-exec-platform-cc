from fastapi import FastAPI
from .routers import functions
from .database.database import engine
from .models import function

# Create database tables
function.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Serverless Function Platform API",
    description="API for managing serverless functions",
    version="1.0.0"
)

# Include routers
app.include_router(functions.router)

@app.get("/")
async def root():
    return {"message": "Welcome to the Serverless Function Platform API"} 