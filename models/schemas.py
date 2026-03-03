"""
Pydantic models for request/response validation.
These define the structure of data flowing through the API.

# ============================================================
# CHANGES FROM ORIGINAL — models.py
# ─────────────────────────────────────────────────────────────
# ADDED: UploadResponse        → returned after a file is indexed
# ADDED: VectorStoreStatus     → returned by /status endpoint
# ADDED: RemoveFileRequest     → body for /remove-file endpoint
# QuestionRequest / QuestionResponse are UNCHANGED.
# ============================================================
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


# ── UNCHANGED ──────────────────────────────────────────────────────────────────

class QuestionRequest(BaseModel):
    """Request model for asking questions"""
    question: str
    model: str

    class Config:
        json_schema_extra = {
            "example": {"question": "How many students are in class 10?"}
        }


class QuestionResponse(BaseModel):
    """Response model for question answers"""
    response: str
    structured_query: Optional[Dict[str, Any]] = None
    raw_result: Optional[Any] = None
    # RAG ADDITION: mode tells the UI which pipeline answered
    mode: Optional[str] = None          # "rag" or "csv"
    rag_sources: Optional[List[Dict]] = None   # chunks used (RAG mode only)

    class Config:
        json_schema_extra = {
            "example": {
                "response": "There are 45 students in class 10.",
                "mode": "csv",
            }
        }


# ── RAG ADDITION: new models ────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    """Returned after a file is successfully indexed."""
    filename: str
    source_type: str
    chunks_added: int
    total_chunks: int
    warning: Optional[str] = None


class VectorStoreStatus(BaseModel):
    """Index stats for the Streamlit sidebar."""
    total_chunks: int
    indexed_files: List[str]
    has_data: bool
    mode: str                          # "rag" or "csv"


class RemoveFileRequest(BaseModel):
    """Body for DELETE /remove-file."""
    filename: str