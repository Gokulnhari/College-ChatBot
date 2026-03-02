"""
Main application entry point.
Starts the FastAPI server.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import router
from config import settings

# Create FastAPI app
app = FastAPI(
    title="School System Query API",
    description="Natural language interface for querying student data",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router, prefix="/api/v1", tags=["queries"])

# Load DataFrame at startup
@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    print("Loading CSV data...")
    df = settings.get_dataframe()
    print(f"Loaded {len(df)} rows")
    print("Application started successfully!")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Auto-reload on code changes
    )
    
    
    
# Chatbot ----> api ----> FastAPI ----> "Give me name of top scorers from each class "----> llm ----> pandas query ---->  execute ---> llm---> english response --->