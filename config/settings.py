"""
Configuration settings for the application.
Centralized place for all constants and configurations.

# ============================================================
# CHANGES FROM ORIGINAL — config.py
# ─────────────────────────────────────────────────────────────
# ADDED: get_mode()         → returns "rag" or "csv" based on index state
# ADDED: RAG_TOP_K          → how many chunks to retrieve per query
# ADDED: SUPPORTED_FORMATS  → list of accepted upload file types
# Everything else is UNCHANGED.
# ============================================================
"""
import pandas as pd
from pathlib import Path


class Settings:
    """Application settings"""

    # ── existing settings (UNCHANGED) ──────────────────────────────────────────
    OLLAMA_URL      = "http://localhost:11434/api/generate"
    OLLAMA_TIMEOUT  = 10000.0

    AVAILABLE_MODELS = {
        "Qwen 2.5":    "qwen2.5:1.5b",
        "Qwen Coder":  "qwen2.5-coder:3b",
        "Llama 3.1":   "llama3.1:8b",
    }
    DEFAULT_MODEL = "qwen2.5:1.5b"

    CSV_FILE_PATH = "school_system_large.csv"

    DEFAULT_LIST_LIMIT = 20

    AVAILABLE_COLUMNS = [
        "Student_ID", "Full_Name", "Gender", "Class", "Section",
        "Math_Marks", "Science_Marks", "English_Marks",
        "Social_Marks", "Computer_Marks",
        "Attendance_Percentage", "Fee_Paid",
    ]

    _df = None
    _uploaded_df = None  # ADDITION: temporary uploaded CSV DataFrame

    @classmethod
    def set_uploaded_dataframe(cls, df) -> None:
        """ADDITION: Set temporary uploaded CSV (session only)"""
        cls._uploaded_df = df

    @classmethod
    def clear_uploaded_dataframe(cls) -> None:
        """ADDITION: Revert to original CSV"""
        cls._uploaded_df = None

    @classmethod
    def get_dataframe(cls) -> pd.DataFrame:
        """MODIFIED: Returns uploaded CSV if present, else original"""
        if cls._uploaded_df is not None:
            return cls._uploaded_df
        if cls._df is None:
            cls._df = pd.read_csv(cls.CSV_FILE_PATH)
        return cls._df

    # ── RAG ADDITION: new settings ─────────────────────────────────────────────
    RAG_TOP_K = 5                    # chunks retrieved per query

    SUPPORTED_FORMATS = [".pdf", ".xlsx", ".xls", ".xml", ".csv"]

    @classmethod
    def get_mode(cls) -> str:
        """
        # RAG ADDITION
        Auto-detect whether to run in RAG mode or CSV mode.

        Logic:
          - If the vector store has indexed data → "rag"
          - Otherwise                            → "csv"

        This is called per-request in routes.py so it reacts live
        when the user uploads a file.
        """
        try:
            from vector_store import vector_store   # local import avoids circular dep
            return "rag" if vector_store.status()["has_data"] else "csv"
        except Exception:
            return "csv"
    # ──────────────────────────────────────────────────────────────────────────


# Create singleton instance
settings = Settings()