"""
Main application entry point.
Starts the FastAPI server.
"""
# ── load_dotenv MUST be first — before any app imports ──────────────────────
from dotenv import load_dotenv
load_dotenv()
# ────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import router
from config import settings
from mcp_tools.mcp_client import mcp_client

app = FastAPI(
    title="School System Query API",
    description="Natural language interface for querying student data",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1", tags=["queries"])

@app.on_event("startup")
async def startup_event():
    print("Loading CSV data...")
    df = settings.get_dataframe()
    print(f"Loaded {len(df)} rows")
    print("Application started successfully!")

    print("[startup] Connecting to MCP server...")      # ← ADD THIS
    await mcp_client.connect()                          # ← ADD THIS
    print("[startup] MCP ready") 

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)