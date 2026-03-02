"""
Pydantic models for request/response validation.
These define the structure of data flowing through the API.
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class QuestionRequest(BaseModel):
    """Request model for asking questions"""
    question: str
    model: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "How many students are in class 10?"
            }
        }

class QuestionResponse(BaseModel):
    """Response model for question answers"""
    response: str
    structured_query: Optional[Dict[str, Any]]=None
    raw_result: Optional[Any]=None
    
    class Config:
        json_schema_extra = {
            "example": {
                "response": "There are 45 students in class 10.",
                "structured_query": {
                    "query_type": "aggregate",
                    "filters": [{"column": "Class", "operator": "==", "value": 10}]
                },
                "raw_result": 45
            }
        }