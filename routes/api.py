"""
API routes for the application.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from embedder import embedder
import json
import re
import httpx

from models import (
    QuestionRequest,
    QuestionResponse,
    UploadResponse,
    VectorStoreStatus,
    RemoveFileRequest,
)
from services import llm_service, query_executor
from config import settings

from vector_store import vector_store
import pandas as pd
import io

from agents.agent_router import detect_agent_intent, parse_email_intent
from agents.email_agent import (
    resolve_recipients,
    get_email_addresses,
    preview_email,
    send_emails,
)
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


# In-memory cache for last fetched record (follow-up support)
_session_cache: Dict[str, Any] = {"last_record": None, "last_filters": None, "last_options": None,}


class EmailPreviewRequest(BaseModel):
    question: str
    model: Optional[str] = None
    parsed_intent: Optional[Dict[str, Any]] = None


class EmailSendRequest(BaseModel):
    intent: Dict[str, Any]
    recipients: List[Dict[str, Any]]
    dry_run: Optional[bool] = False


router = APIRouter()


def extract_potential_full_name(question: str) -> str | None:
    match = re.search(
        r"(?:who is|tell me about|details of(?: the student)?|"
        r"fetch(?: the)? details of(?: the student)?|"
        r"show details of|get details of|find|search for)\s+"
        r"([A-Za-z]+(?: [A-Za-z]+)+)",
        question,
        re.IGNORECASE
    )
    
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


def _try_direct_answer(structured_query: dict, result: any) -> str | None:
    query_type = structured_query.get("query_type")

    if isinstance(result, list) and len(result) == 1:
        row = result[0]
        if isinstance(row, dict) and len(row) == 1:
            val = list(row.values())[0]
            if isinstance(val, (int, float)):
                fn        = structured_query.get("aggregation", {}).get("function", "")
                label_map = {"count": "total", "sum": "total", "avg": "average",
                             "mean": "average", "min": "minimum", "max": "maximum"}
                label = label_map.get(fn.lower(), "result")
                if isinstance(val, float) and val == int(val):
                    val = int(val)
                elif isinstance(val, float):
                    val = round(val, 2)
                return f"The {label} is **{val}**."

    if isinstance(result, pd.DataFrame) and not result.empty:
        if query_type == "aggregate" and result.shape == (1, 1):
            col        = result.columns[0]
            value      = result.iloc[0, 0]
            fn         = structured_query.get("aggregation", {}).get("function", "")
            label_map  = {"count": "total", "sum": "total", "avg": "average",
                          "mean": "average", "min": "minimum", "max": "maximum"}
            label      = label_map.get(fn.lower(), fn)
            pretty_col = col.replace("_", " ").lower()
            if isinstance(value, float) and value == int(value):
                value = int(value)
            elif isinstance(value, float):
                value = round(value, 2)
            return f"The {label} {pretty_col} is **{value}**."

    return None


# ── /upload ────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    allowed_extensions = set(settings.SUPPORTED_FORMATS)
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_extensions)}"
        )

    file_bytes = await file.read()

    if ext == ".csv":
        try:
            df = pd.read_csv(io.BytesIO(file_bytes))
            settings.set_uploaded_dataframe(df, filename=filename)
            query_executor.df = df
            print(f"[upload] CSV loaded: {df.shape}, columns: {list(df.columns)}")
            return UploadResponse(
                filename=filename, source_type="csv",
                chunks_added=len(df), total_chunks=len(df),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"CSV load error: {str(e)}")

    if ext in (".xlsx", ".xls"):
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
            settings.set_uploaded_dataframe(df, filename=filename)
            query_executor.df = df
            print(f"[upload] Excel loaded: {df.shape}, columns: {list(df.columns)}")
            return UploadResponse(
                filename=filename, source_type="excel",
                chunks_added=len(df), total_chunks=len(df),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Excel load error: {str(e)}")

    try:
        result = vector_store.add_file(filename, file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing error: {str(e)}")

    return UploadResponse(**result)


# ── /status ────────────────────────────────────────────────────────────────────

@router.get("/status", response_model=VectorStoreStatus)
async def get_status():
    stats = vector_store.status()
    mode  = settings.get_mode()
    return VectorStoreStatus(**stats, mode=mode)


# ── /health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    health_data = {"status": "healthy", "issues": []}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            response = await client.get(settings.OLLAMA_URL.replace("/api/generate", "/api/tags"))
            response.raise_for_status()
            models = response.json().get("models", [])
            available_models = [m["name"] for m in models] if models else []
            health_data["ollama"] = {"status": "healthy", "url": settings.OLLAMA_URL,
                                     "available_models": available_models}
    except Exception as e:
        health_data["status"] = "degraded"
        health_data["issues"].append("Ollama service is not available")
        health_data["ollama"] = {"status": f"unhealthy: {str(e)}", "url": settings.OLLAMA_URL,
                                 "available_models": []}
    try:
        health_data["vector_store"] = vector_store.status()
    except Exception as e:
        health_data["issues"].append(f"Vector store error: {str(e)}")
        health_data["vector_store"] = {"status": "error"}
    try:
        df = settings.get_dataframe()
        health_data["csv_data"] = {"status": f"loaded ({len(df)} rows)" if df is not None else "not loaded"}
    except Exception as e:
        health_data["issues"].append(f"CSV data error: {str(e)}")
        health_data["csv_data"] = {"status": "error"}
    return health_data


# ── /remove-file ───────────────────────────────────────────────────────────────

@router.post("/remove-file")
async def remove_file(request: RemoveFileRequest):
    if request.filename.endswith(".csv") or request.filename.endswith((".xlsx", ".xls")):
        settings.clear_uploaded_dataframe()
        query_executor.df = settings.get_dataframe()
        return {"filename": request.filename, "removed": 1,
                "message": "Uploaded file cleared. Reverted to original database."}
    result = vector_store.remove_file(request.filename)
    return result


# ── /agent/email/preview ───────────────────────────────────────────────────────

@router.post("/agent/email/preview")
async def agent_email_preview(request: EmailPreviewRequest):
    try:
        intent = request.parsed_intent if request.parsed_intent else \
                 await parse_email_intent(request.question, request.model)

        print(f"[email_preview] intent filters: {intent.get('filters')}")

        import re as _re
        _id_match = _re.search(r'\b(\d{3,6})\b', request.question)
        if _id_match:
            extracted_id = int(_id_match.group(1))
            filters = intent.get("filters", [])
            for f in filters:
                col = f.get("column") or f.get("field")
                if col == "Student_ID":
                    f["value"] = extracted_id
            if not any((f.get("column") or f.get("field")) == "Student_ID" for f in filters):
                filters.append({"column": "Student_ID", "operator": "==", "value": extracted_id})
                intent["filters"] = filters

        df      = settings.get_dataframe()
        filters = intent.get("filters", [])

        for f in filters:
            col = f.get("column") or f.get("field")
            val = f.get("value")
            if col and col in df.columns and pd.api.types.is_numeric_dtype(df[col].dtype):
                try:
                    f["value"] = int(val) if "." not in str(val) else float(val)
                except (ValueError, TypeError):
                    pass

        matched_df = resolve_recipients(filters, df) if filters else df

        if matched_df.empty:
            return {"intent": intent, "preview": None,
                    "warning": "No students matched the given filters.", "recipients": []}

        target     = intent.get("target", "student")
        recipients = get_email_addresses(matched_df, target)
        prv        = preview_email(intent, recipients)

        has_real_emails = any("@school.placeholder" not in r["email"] for r in recipients)
        warning = None if has_real_emails else (
            "⚠️ No email column found. Add an 'Email' or 'Parent_Email' column to your CSV."
        )

        return {"intent": intent, "preview": prv, "warning": warning, "recipients": recipients}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email preview error: {str(e)}")


# ── /agent/email/send ──────────────────────────────────────────────────────────

@router.post("/agent/email/send")
async def agent_email_send(request: EmailSendRequest):
    try:
        result = send_emails(
            intent=request.intent, recipients=request.recipients, dry_run=request.dry_run,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email send error: {str(e)}")


# ── /ask ───────────────────────────────────────────────────────────────────────

@router.post("/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest):
    print(f"\n{'='*70}")
    print(f"[ASK] Question: {request.question}")
    print(f"[ASK] Model: {request.model}")

    conversation_history = request.conversation_history or []

    # --- Custom agent instruction injection ---
    if request.selected_agent:
        from agents.agent_builder import load_custom_agents
        custom_agents = load_custom_agents()
        active_agent = next(
            (a for a in custom_agents if a["name"] == request.selected_agent), None
        )
        if active_agent and active_agent.get("instructions"):
            conversation_history = [
                {"role": "system", "content": active_agent["instructions"]}
            ] + conversation_history
    # --- end injection ---

    # ✅ NEW — resolve "option 1/2/3" BEFORE anything else
    q_stripped = request.question.strip().lower()
    option_match = re.match(r'^option\s*(\d+)$', q_stripped)
    if option_match and _session_cache.get("last_options"):
        option_idx = int(option_match.group(1)) - 1   # 0-indexed
        options    = _session_cache["last_options"]

        if 0 <= option_idx < len(options):
            chosen = options[option_idx]
            print(f"[routes] Option resolved: {chosen}")

            # Build a direct filter query using the chosen record's ID
            df     = settings.get_dataframe()
            id_col = next((c for c in df.columns if "id" in c.lower()), None)
            name_col = next((c for c in df.columns if "name" in c.lower()), None)

            if id_col and id_col in chosen:
                chosen_id = chosen[id_col]
                # Fetch the full record directly — no LLM involved
                matched = df[df[id_col] == chosen_id].to_dict(orient="records")
                if matched:
                    record = matched[0]
                    _session_cache["last_record"]  = record
                    _session_cache["last_options"] = None   # clear options
                    parts = [
                        f"**{k.replace('_', ' ')}:** {v}"
                        for k, v in record.items()
                        if v not in (None, "", "nan")
                    ]
                    return QuestionResponse(
                        response="\n".join(parts),
                        structured_query={"query_type": "filter",
                                          "filters": [{
                                              "column": id_col,
                                              "operator": "==",
                                              "value": chosen_id
                                          }]},
                        raw_result=record,
                        mode="csv",
                    )

        # Invalid option number
        return QuestionResponse(
            response=f"Please choose a valid option (1 to {len(options)}).",
            structured_query=None, raw_result=None, mode="csv",
        )

    agent_intent = await detect_agent_intent(request.question, request.model)
    print(f"[ASK] Agent intent: {agent_intent}")

    if agent_intent == "send_email":
        parsed_intent = await parse_email_intent(request.question, request.model)
        return QuestionResponse(
            response=(
                "📧 I can help you send that email! "
                "Let me find the recipients and prepare a preview for you to review before sending."
            ),
            structured_query={"agent": "email", "trigger": request.question,
                               "parsed_intent": parsed_intent},
            raw_result=None, mode="agent",
        )

    override = request.mode_override
    if override == "CSV only (student database)":
        mode = "csv"
    elif override == "RAG only (uploaded documents)":
        mode = "rag"
    else:
        mode = settings.get_mode()
    print(f"[routes] Mode: {mode}")

    if mode == "rag":
        rag_intent  = await llm_service.classify_rag_intent(request.question, model_name=request.model)
        intent      = rag_intent["intent"]
        search_hint = rag_intent["retrieval_hint"]

        if intent == "summarize":
           chunks = [
                {"text": c["text"], "filename": c["filename"],
                "source_type": c["source_type"], "score": 1.0, "meta": c.get("meta", {})}
                for c in embedder._chunks[:12]   # up from 4, no 500-char truncation
            ]
        else:
            import re as _re
            entities = _re.findall(r'\b[A-Z][a-zA-Z]+\b', request.question)
            for entity in entities:
                if entity not in search_hint and entity not in (
                        "Give", "What", "How", "Why", "Tell", "Show"):
                    search_hint = f"{entity} {search_hint}"
                    break
            top_k  = rag_intent["top_k"]
            chunks = vector_store.search(search_hint, top_k=top_k)

        print(f"[RAG] intent={intent} | search_hint='{search_hint}' | "
              f"top_k={rag_intent['top_k']} | chunks_found={len(chunks)}")

        seen, unique_chunks = set(), []
        for c in chunks:
            key = c["text"][:100]
            if key not in seen:
                seen.add(key)
                unique_chunks.append(c)
        chunks = unique_chunks[:4]
        if chunks:
            chunks[0]["intent"] = intent

        if not chunks:
            return QuestionResponse(
                response="I couldn't find relevant information in the uploaded documents.",
                mode="rag", rag_sources=[],
            )

        answer = await llm_service.rag_answer(
            question=request.question, chunks=chunks, model_name=request.model,
        )
        return QuestionResponse(response=answer, mode="rag", rag_sources=chunks)

    # ── CSV pipeline ───────────────────────────────────────────────────────────
    question_type = await llm_service.classify_question(
        request.question, model_name=request.model,
        conversation_history=conversation_history
    )

    if question_type == "general":
        chat_response = await llm_service.generate_chat_response(
            request.question, model_name=request.model,
            conversation_history=conversation_history,
        )
        return QuestionResponse(response=chat_response, structured_query=None,
                                raw_result=None, mode="csv")

    potential_name = extract_potential_full_name(request.question)

    if potential_name:
        df       = settings.get_dataframe()
        name_col = next((c for c in df.columns if "name" in c.lower()), None)
        if name_col:
            matching_students = df[df[name_col].str.contains(
                potential_name, case=False, na=False)]
        else:
            matching_students = pd.DataFrame()

        if len(matching_students) > 1:
            cols = [name_col] if name_col else []
            for c in ["Class", "Section", "Student_ID"]:
                if c in df.columns:
                    cols.append(c)
            options = matching_students[cols].to_dict(orient="records")

            _session_cache["last_options"] = matching_students.to_dict(orient="records")
            
            natural_response = (
                f"There are multiple students named '{potential_name}'. "
                f"Which one are you referring to?\n\nOptions:\n"
            )
            for i, option in enumerate(options):
                natural_response += f"{i+1}. " + \
                    ", ".join(f"{k}: {v}" for k, v in option.items()) + "\n"
            return QuestionResponse(
                response=natural_response,
                structured_query={"query_type": "clarification",
                                  "question": f"Which '{potential_name}'?",
                                  "options": options},
                raw_result=None, mode="csv",
            )

    import re as _re
    _q_lower     = request.question.lower()
    _id_keywords = ["id", "number", "no", "mrn", "stu", "emp", "roll", "reg"]
    _has_id_context = any(kw in _q_lower for kw in _id_keywords)

    if _has_id_context:
        _id_match     = _re.search(r'\b([A-Z]{1,6}[-_]?\d{3,12}|\d{3,12})\b', request.question)
        _extracted_id = _id_match.group(1) if _id_match else None
    else:
        _extracted_id = None

    # ── Follow-up check (BEFORE structured query) — column-name based ─────────
    # Works for any dataset — no hardcoded column names or phrases
    if _session_cache.get("last_record"):
        record  = _session_cache["last_record"]
        q_lower = request.question.lower()

        matched_col = None
        matched_val = None
        for col, val in record.items():
            col_variations = [
                col.lower(),
                col.lower().replace("_", " "),
                col.lower().replace("_", ""),
            ]
            if any(variation in q_lower for variation in col_variations):
                matched_col = col
                matched_val = val
                break

        # General follow-up phrases (no specific column mentioned)
        general_followup = any(phrase in q_lower for phrase in [
            "that student", "same student", "fetched earlier",
            "previously", "just fetched", "the one", "that record",
            "same person", "that person",
        ])

        if matched_col:
            name_col = next((k for k in record if "name" in k.lower()), None)
            name     = record.get(name_col, "the record") if name_col else "the record"
            return QuestionResponse(
                response=f"The {matched_col.replace('_', ' ')} of {name} is **{matched_val}**.",
                structured_query=None, raw_result=record, mode="csv",
            )
        elif general_followup:
            lines = "\n".join(f"- **{k.replace('_', ' ')}**: {v}"
                              for k, v in record.items())
            return QuestionResponse(
                response=f"Here are the details:\n{lines}",
                structured_query=None, raw_result=record, mode="csv",
            )
    # ─────────────────────────────────────────────────────────────────────────

    # ── Structured query (LLM) ────────────────────────────────────────────────
    structured_query = await llm_service.get_structured_query(
        request.question, model_name=request.model,
        conversation_history=conversation_history
    )

    # Sanitize columns against actual DataFrame
    try:
        df          = settings.get_dataframe()
        actual_cols = list(df.columns) if df is not None else []
        print(f"[query_planner] df shape: {df.shape if df is not None else 'None'}")
        print(f"[query_planner] query_executor.df shape: "
              f"{query_executor.df.shape if query_executor.df is not None else 'None'}")

        if structured_query.get("select_columns"):
            valid_cols = [c for c in structured_query["select_columns"] if c in actual_cols]
            structured_query["select_columns"] = valid_cols if len(valid_cols) >= 5 else None

        if structured_query.get("filters"):
            structured_query["filters"] = [
                f for f in structured_query["filters"]
                if (f.get("column") or f.get("field")) in actual_cols
            ]

        if structured_query.get("sort_by"):
            sort_col = structured_query["sort_by"].get("column")
            if not sort_col or sort_col not in actual_cols:
                structured_query["sort_by"] = None

    except Exception:
        pass

    # ← ADD: fix aggregate query with missing aggregations
    if structured_query.get("query_type") == "aggregate":
        aggs = structured_query.get("aggregations")
        if not aggs or aggs == [None]:
            try:
                df     = settings.get_dataframe()
                id_col = next(
                    (c for c in df.columns if "id" in c.lower()),
                    df.columns[0]
                )
            except Exception:
                id_col = "Student_ID"
            structured_query["aggregations"] = [
                {"function": "count", "column": id_col, "alias": "total"}
            ]
            print(f"[routes] Fixed missing aggregations → count on {id_col}")

    # Inject extracted ID if LLM missed it
    if _extracted_id:
        if structured_query.get("filters") is None:
            structured_query["filters"] = []
        if isinstance(structured_query["filters"], list):
            filters = structured_query["filters"]
            try:
                df     = settings.get_dataframe()
                id_col = next((c for c in df.columns if "id" in c.lower()), "Student_ID")
            except Exception:
                id_col = "Student_ID"
            has_id_filter = any(
                f.get("column") == id_col or f.get("field") == id_col
                for f in filters
            )
            if not has_id_filter:
                val = int(_extracted_id) if _extracted_id.isdigit() else _extracted_id
                filters.append({"column": id_col, "operator": "==", "value": val})

    if structured_query.get("query_type") == "error":
        return QuestionResponse(
            response=structured_query.get("error", "Sorry, I encountered an error."),
            structured_query=None, raw_result=None, mode="csv",
        )

    if structured_query.get("query_type") == "clarification":
        clarification_question = structured_query.get("question", "Please clarify your request.")
        options_list = []
        for option in structured_query.get("options", []):
            if isinstance(option, dict):
                options_list.append(f"- {', '.join([f'{k}: {v}' for k, v in option.items()])}")
            else:
                options_list.append(f"- {option}")
        return QuestionResponse(
            response=f"{clarification_question}\n\nOptions:\n" + "\n".join(options_list),
            structured_query=structured_query, raw_result=None, mode="csv",
        )

    print(f"[routes] structured_query: {structured_query}")
    result = query_executor.execute(structured_query)
    print(f"[routes] result: {result}, type: {type(result).__name__}")

    # Cache single record for follow-up questions
    if isinstance(result, list) and len(result) == 1:
        _session_cache["last_record"]  = result[0]
        _session_cache["last_filters"] = structured_query.get("filters", [])

    natural_response = _try_direct_answer(structured_query, result)
    print(f"[routes] _try_direct_answer returned: {natural_response}")
    if natural_response is None:
        natural_response = await llm_service.generate_natural_response(
            request.question, result, model_name=request.model
        )

    return QuestionResponse(
        response=natural_response, structured_query=structured_query,
        raw_result=result, mode="csv",
    )
    



# ── /active-csv ────────────────────────────────────────────────────────────────

@router.get("/active-csv")
async def active_csv_status():
    from config import settings as s
    if s._uploaded_df is not None:
        df    = s._uploaded_df
        fname = getattr(s, '_uploaded_filename', None) or 'uploaded_file.csv'
        return {"uploaded": True, "filename": fname,
                "rows": len(df), "columns": len(df.columns)}
    return {"uploaded": False}


@router.get("/domain-info")
async def get_domain_info():
    from config.domains import list_domains
    domain = settings.get_domain()
    return {
        "current_domain":    settings.ACTIVE_DOMAIN,
        "available_domains": list_domains(),
        "entity_name":       domain.entity_name,
        "entity_plural":     domain.entity_name_plural,
        "description":       domain.description,
        "csv_file":          domain.csv_file_path,
        "field_count":       len(domain.fields),
        "fields":            domain.field_names,
    }


@router.post("/set-domain")
async def set_domain(request: dict):
    domain_name = request.get("domain_name")
    if not domain_name:
        raise HTTPException(status_code=400, detail="domain_name is required")
    try:
        from config.domains import list_domains
        if domain_name not in list_domains():
            raise HTTPException(
                status_code=400,
                detail=f"Invalid domain. Available: {', '.join(list_domains())}"
            )
        settings.set_domain(domain_name)
        query_executor.df = None
        domain = settings.get_domain()
        return {"domain": domain_name, "entity_plural": domain.entity_name_plural,
                "csv_file": domain.csv_file_path, "fields": domain.field_names,
                "status": "switched"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error switching domain: {str(e)}")