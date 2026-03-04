"""
API routes for the application.
Defines all HTTP endpoints.

# ============================================================
# CHANGES FROM ORIGINAL — routes.py
# ─────────────────────────────────────────────────────────────
# ADDED: POST /upload        → index a new file into the RAG store
# ADDED: GET  /status        → return index stats
# ADDED: POST /remove-file   → remove a file from the index
# MODIFIED: POST /ask        → auto-routes to RAG or CSV pipeline
#           based on settings.get_mode().
#           The entire original CSV pipeline is preserved and only
#           skipped when RAG mode is active.
# ============================================================
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
import json
import re

from models import (
    QuestionRequest,
    QuestionResponse,
    UploadResponse,
    VectorStoreStatus,
    RemoveFileRequest,
)
from services import llm_service, query_executor
from config import settings

# RAG ADDITION: import new modules
from vector_store import vector_store
import pandas as pd  # ADDITION
import io            # ADDITION

router = APIRouter()


# ── UNCHANGED helper ───────────────────────────────────────────────────────────

def extract_potential_full_name(question: str) -> str | None:
    match = re.search(r"(?:who is|tell me about)\s+([A-Za-z\s]+?)\??$", question, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    name_parts = []
    segments = re.split(r'\s(?:and|or)\s', question)
    for segment in segments:
        words = segment.split()
        current_name_parts = []
        for word in words:
            if re.match(r'^[A-Z][a-z]*$', word) or re.match(r'^[A-Z]+$', word):
                current_name_parts.append(word)
            elif current_name_parts:
                break
        if len(current_name_parts) >= 2:
            name_parts.append(" ".join(current_name_parts))

    return name_parts[0] if name_parts else None


# ── RAG ADDITION: /upload endpoint ────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """
    # RAG ADDITION
    Upload a PDF, Excel, XML, or CSV file to be indexed for RAG retrieval.

    - Reads raw bytes from the upload
    - Dispatches to file_processor → chunker → embedder
    - Saves the updated index to disk
    - Returns chunk count and file metadata
    """
    allowed_extensions = set(settings.SUPPORTED_FORMATS)
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_extensions)}"
        )

    file_bytes = await file.read()

        # ADDITION: CSV files load into pandas, not RAG
    if ext == ".csv":
        try:
            df = pd.read_csv(io.BytesIO(file_bytes))
            settings.set_uploaded_dataframe(df)
            # Update query_executor to use new DataFrame
            query_executor.df = df
            return UploadResponse(
                filename=filename,
                source_type="csv",
                chunks_added=len(df),
                total_chunks=len(df),
                warning=f"CSV loaded into pandas with {len(df)} rows and columns: {', '.join(df.columns.tolist())}"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"CSV load error: {str(e)}")
    # ADDITION END

    try:
        result = vector_store.add_file(filename, file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing error: {str(e)}")

    return UploadResponse(**result)

    


# ── RAG ADDITION: /status endpoint ────────────────────────────────────────────

@router.get("/status", response_model=VectorStoreStatus)
async def get_status():
    """
    # RAG ADDITION
    Return vector store stats and current mode (rag / csv).
    Called by the Streamlit sidebar to show indexed files.
    """
    stats = vector_store.status()
    mode  = settings.get_mode()
    return VectorStoreStatus(**stats, mode=mode)


# ── RAG ADDITION: /remove-file endpoint ───────────────────────────────────────

@router.post("/remove-file")
async def remove_file(request: RemoveFileRequest):
    if request.filename.endswith(".csv"):
        # Clear pandas uploaded DataFrame
        settings.clear_uploaded_dataframe()
        query_executor.df = settings.get_dataframe()
        # Also remove from RAG in case it was indexed in a previous session
        vector_store.remove_file(request.filename)
        return {"filename": request.filename, "removed": 1,
                "message": "Uploaded CSV cleared. Reverted to original database."}
    result = vector_store.remove_file(request.filename)
    return result


# ── MODIFIED: /ask endpoint ────────────────────────────────────────────────────

@router.post("/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest):
    """
    Answer a natural language question.

    # MODIFICATION: Auto-detects mode at request time.
    # ─────────────────────────────────────────────────
    # If files have been uploaded (RAG mode):
    #   1. Retrieve top-K relevant chunks from the vector store
    #   2. Pass chunks + question to rag_answer() in llm_service
    #   3. Return answer with source citations
    #
    # If no files uploaded (CSV mode):
    #   → Entire original pipeline runs UNCHANGED
    # ─────────────────────────────────────────────────
    """
    print(f"Question: {request.question}")
    print(f"Selected Model: {request.model}")

    # ── RAG ADDITION: mode detection ──────────────────────────────────────────
    override = request.mode_override
    if override == "CSV only (student database)":
        mode = "csv"
    elif override == "RAG only (uploaded documents)":
        mode = "rag"
    else:
        mode = settings.get_mode()
    print(f"[routes] Mode: {mode}")

    if mode == "rag":
        # ── RAG PIPELINE ──────────────────────────────────────────────────────

        # Retrieve relevant chunks
        chunks = vector_store.search(request.question, top_k=settings.RAG_TOP_K)

        if not chunks:
            return QuestionResponse(
                response="I couldn't find relevant information in the uploaded documents. "
                         "Please make sure you've uploaded the correct files.",
                mode="rag",
                rag_sources=[],
            )

        # Generate answer grounded in retrieved context
        answer = await llm_service.rag_answer(
            question=request.question,
            chunks=chunks,
            model_name=request.model,
        )

        return QuestionResponse(
            response=answer,
            mode="rag",
            rag_sources=chunks,           # returned for the UI to display citations
        )
    # ── END RAG ADDITION ──────────────────────────────────────────────────────

    # ── ORIGINAL CSV PIPELINE (100% unchanged below this line) ────────────────

    # Step 0: Classify question
    question_type = await llm_service.classify_question(
        request.question,
        model_name=request.model
    )
    print("Question Type:", question_type)

    if question_type == "general":
        chat_response = await llm_service.generate_chat_response(
            request.question,
            model_name=request.model
        )
        return QuestionResponse(
            response=chat_response,
            structured_query=None,
            raw_result=None,
            mode="csv",
        )

    # Pre-step: Check for ambiguous names directly from the data
    potential_name = extract_potential_full_name(request.question)

    if potential_name:
        df = settings.get_dataframe()
        matching_students = df[df["Full_Name"].str.contains(potential_name, case=False, na=False)]

        if len(matching_students) > 1:
            options = matching_students[["Full_Name", "Class", "Section", "Student_ID"]].to_dict(orient="records")

            natural_response = (
                f"There are multiple students named '{potential_name}'. "
                f"Which one are you referring to?\n\nOptions:\n"
            )
            for i, option in enumerate(options):
                natural_response += (
                    f"{i+1}. Name: {option['Full_Name']}, Class: {option['Class']}, "
                    f"Section: {option['Section']}, Student ID: {option['Student_ID']}\n"
                )

            return QuestionResponse(
                response=natural_response,
                structured_query={
                    "query_type": "clarification",
                    "question": f"Which '{potential_name}' are you referring to?",
                    "options": options,
                },
                raw_result=None,
                mode="csv",
            )

    # Step 1: Get structured query from LLM
    structured_query = await llm_service.get_structured_query(
        request.question, model_name=request.model
    )
    print(f"Structured Query: {json.dumps(structured_query, indent=2)}")

    if structured_query.get("query_type") == "clarification":
        clarification_question = structured_query.get("question", "Please clarify your request.")
        options = structured_query.get("options", [])
        options_str = "\n".join([
            f"- {', '.join([f'{k}: {v}' for k, v in option.items()])}"
            for option in options
        ])
        return QuestionResponse(
            response=f"{clarification_question}\n\nOptions:\n{options_str}",
            structured_query=structured_query,
            raw_result=None,
            mode="csv",
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
        raw_result=result,
        mode="csv",
    )


# ── UNCHANGED: /health endpoint ───────────────────────────────────────────────

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

# ADDITION: active CSV status endpoint
@router.get("/active-csv")
async def active_csv_status():
    """Returns info about the currently active CSV"""
    from config import settings as s
    if s._uploaded_df is not None:
        df = s._uploaded_df
        return {
            "uploaded": True,
            "filename": "uploaded_file.csv",
            "rows": len(df),
            "columns": len(df.columns)
        }
    return {"uploaded": False}
