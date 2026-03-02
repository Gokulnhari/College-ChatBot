"""
API routes for the application.
Defines all HTTP endpoints.
"""
from fastapi import APIRouter
import json
import re

from models import QuestionRequest, QuestionResponse
from services import llm_service, query_executor
from config import settings

router = APIRouter()

def extract_potential_full_name(question: str) -> str | None:
    # Pattern 1: "who is [Name]?" or "tell me about [Name]"
    match = re.search(r"(?:who is|tell me about)\s+([A-Za-z\s]+?)\??$", question, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Pattern 2: Identify capitalized words that could be a name at the beginning or within a phrase.
    # This is a more aggressive approach, looking for sequences of capitalized words.
    # E.g., "Meera Sharma's scores" -> "Meera Sharma"
    # E.g., "Highest score for Meera Sharma" -> "Meera Sharma"
    name_parts = []
    # Split by common delimiters like ' and '
    segments = re.split(r'\s(?:and|or)\s', question)
    for segment in segments:
        words = segment.split()
        current_name_parts = []
        for word in words:
            # A word starting with an uppercase letter followed by lowercase, or fully uppercase
            if re.match(r'^[A-Z][a-z]*$', word) or re.match(r'^[A-Z]+$', word):
                current_name_parts.append(word)
            elif current_name_parts: # If we've started collecting name parts and hit a non-name word
                break # Stop collecting for this segment
        
        # If we found at least two capitalized words, consider it a name
        if len(current_name_parts) >= 2:
            name_parts.append(" ".join(current_name_parts))
    
    if name_parts:
        # For simplicity, just return the first potential full name found.
        # More complex logic could try to resolve multiple names.
        return name_parts[0]

    return None


@router.post("/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest):
    """
    Answer a natural language question about the student data.
    
    Process:
    1. Convert question to structured query using LLM
    2. Execute query on DataFrame safely
    3. Convert result to natural language using LLM
    
    Args:
        request: QuestionRequest containing the user's question
        
    Returns:
        QuestionResponse with natural language answer and debug info
    """
    print(f"Question: {request.question}")
    print(f"Selected Model: {request.model}")
    
        # Step 0: Classify question
    question_type = await llm_service.classify_question(
        request.question,
        model_name=request.model
    )

    print("Question Type:", question_type)

    # If general chat → directly respond
    if question_type == "general":
        chat_response = await llm_service.generate_chat_response(
            request.question,
            model_name=request.model
        )

        return QuestionResponse(
            response=chat_response,
            structured_query=None,
            raw_result=None
        )

    # Otherwise → database flow continues

    # Pre-step: Check for ambiguous names directly from the data
    potential_name = extract_potential_full_name(request.question)
    
    if potential_name:
        df = settings.get_dataframe()
        matching_students = df[df["Full_Name"].str.contains(potential_name, case=False, na=False)]
        
        if len(matching_students) > 1:
            # Found multiple students with the same name, create clarification response
            options = matching_students[["Full_Name", "Class", "Section", "Student_ID"]].to_dict(orient="records")
            
            natural_response = (
                f"There are multiple students named '{potential_name}'. "
                f"Which one are you referring to?\n\nOptions:\n"
            )
            for i, option in enumerate(options):
                natural_response += f"{i+1}. Name: {option['Full_Name']}, Class: {option['Class']}, Section: {option['Section']}, Student ID: {option['Student_ID']}\n"
            
            clarification_structured_query = {
                "query_type": "clarification",
                "question": f"Which '{potential_name}' are you referring to?",
                "options": options
            }
            
            return QuestionResponse(
                response=natural_response,
                structured_query=clarification_structured_query,
                raw_result=None
            )
            
    # Step 1: Get structured query from LLM
    structured_query = await llm_service.get_structured_query(request.question,model_name=request.model)
    print(f"Structured Query: {json.dumps(structured_query, indent=2)}")

    # Check for clarification query type
    if structured_query.get("query_type") == "clarification":
        clarification_question = structured_query.get("question", "Please clarify your request.")
        options = structured_query.get("options", [])
        
        # Format options for the user
        options_str = "\n".join([
            f"- {', '.join([f'{k}: {v}' for k, v in option.items()])}"
            for option in options
        ])
        
        natural_response = f"{clarification_question}\n\nOptions:\n{options_str}"
        
        return QuestionResponse(
            response=natural_response, 
            structured_query=structured_query,
            raw_result=None # No raw result for clarification
        )
    
    # Step 2: Execute query on DataFrame
    result = query_executor.execute(structured_query)
    print(f"Result: {result}")
    
    # Step 3: Generate natural language response
    natural_response = await llm_service.generate_natural_response(
        request.question, 
        result,
        model_name=request.model
    )
    print(f"Natural Response: {natural_response}")
    
    return QuestionResponse(
        response=natural_response,
        structured_query=structured_query,
        raw_result=result
    )

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}