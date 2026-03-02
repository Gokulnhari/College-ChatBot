"""
Configuration settings for the application.
Centralized place for all constants and configurations.
"""
import pandas as pd
from pathlib import Path

class Settings:
    """Application settings"""
    
    # API Configuration
    OLLAMA_URL = "http://localhost:11434/api/generate"     
    OLLAMA_TIMEOUT = 10000.0
    
    # LLM Models
    AVAILABLE_MODELS = {
        "Qwen 2.5": "qwen2.5:1.5b",
        "Qwen Coder": "qwen2.5-coder:3b",
        "Llama 3.1": "llama3.1:8b",
    }
    # Default model for query planning and response generation
    DEFAULT_MODEL = "qwen2.5:1.5b"
    
    # Data Configuration
    CSV_FILE_PATH = "school_system_large.csv"
    
    # Query Configuration
    DEFAULT_LIST_LIMIT = 20
    
    # Available columns in the dataset
    AVAILABLE_COLUMNS = [
        "Student_ID", "Full_Name", "Gender", "Class", "Section", 
        "Math_Marks", "Science_Marks", "English_Marks", 
        "Social_Marks", "Computer_Marks", 
        "Attendance_Percentage", "Fee_Paid"
    ]
    
    # Load DataFrame once at startup
    _df = None
    
    @classmethod
    def get_dataframe(cls) -> pd.DataFrame:
        """Get the cached DataFrame (loads once)"""
        if cls._df is None:
            cls._df = pd.read_csv(cls.CSV_FILE_PATH)
        return cls._df

# Create singleton instance
settings = Settings()