"""
LLM service for making API calls to Ollama.
Handles all interactions with the language model.
"""
import httpx
import json
import re
from typing import Dict, Any, List

import importlib
import prompts
importlib.reload(prompts)

from config import settings
from prompts import QUERY_PLANNER_PROMPT, RESPONSE_GENERATOR_PROMPT
from prompts.templates import (
    get_classification_prompt,
    get_query_planner_prompt,
    get_response_generator_prompt,
    get_rag_prompt
)


class LLMService:

    def __init__(self):
        self.url           = settings.OLLAMA_URL
        self.timeout       = httpx.Timeout(settings.OLLAMA_TIMEOUT)
        self.default_model = settings.DEFAULT_MODEL

    # ── classify_question ─────────────────────────────────────────────────────

    async def classify_question(self, question: str, model_name: str = None, conversation_history: List[Dict] = None) -> str:
        question_lower = question.lower().strip()

        # HEURISTIC 3: Obvious database keywords → always database
        # Bypasses LLM entirely for clear data queries
        database_keywords = [
            "count", "total", "how many", "average", "marks", "attendance",
            "score", "grade", "fee", "student", "class", "section", "rank",
            "top", "bottom", "highest", "lowest", "pass", "fail", "list"
        ]
        if any(kw in question_lower for kw in database_keywords):
            print(f"[classify] Keyword match: '{question}' → database")
            return "database"

        personal_patterns = [
            "my name", "what is my", "who am i", "do you remember",
            "what did i say", "what did i tell", "i told you", "i said",
            "you are", "your name", "who are you", "how are you",
        ]
        if any(p in question_lower for p in personal_patterns):
            print(f"[classify] Personal question detected: '{question}' → general")
            return "general"

        # ── Database follow-up patterns ────────────────────────────────────────
        follow_up_patterns = [
            "whats the name", "what is the name", "the name of",
            "their name", "his name", "her name",
            "same student", "that student", "this student",
            "full details", "more details", "all details",
            "full information", "more information",
            "tell me more", "show more",
        ]
        if any(p in question_lower for p in follow_up_patterns):
            if not any(kw in question_lower for kw in ["email", "send", "mail", "notify"]):
                print(f"[classify] Follow-up pattern detected: '{question}' → database")
                return "database"
        # ──────────────────────────────────────────────────────────────────────

        if conversation_history and len(conversation_history) > 0:
            word_count = len(question_lower.split())
            if word_count <= 3:
                last_user_msg = next((msg for msg in reversed(conversation_history) if msg['role'] == 'user'), None)
                if last_user_msg:
                    domain = settings.get_domain()
                    entity_mentioned = any(entity in last_user_msg['content'].lower()
                                          for entity in [domain.entity_name, domain.entity_name_plural])
                    field_mentioned = any(field.lower() in last_user_msg['content'].lower()
                                         for field in domain.field_names[:10])
                    if entity_mentioned or field_mentioned:
                        print(f"[classify] Short follow-up detected: '{question}' → database")
                        return "database"

        model_to_use = model_name if model_name else self.default_model
        domain       = settings.get_domain()
        prompt       = get_classification_prompt(domain, question)

        print(f"[classify] Classifying: '{question}' (history: {len(conversation_history or [])} turns)")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={"model": model_to_use, "prompt": prompt, "stream": False}
                )
                response.raise_for_status()

            data       = response.json()
            raw        = data.get("response", "").strip().lower()
            first_word = raw.splitlines()[0].strip().split()[0] if raw.strip() else "general"

            classification = "database" if first_word == "database" else "general"
            print(f"[classify] Result: {classification} (LLM output: '{raw[:60]}')")
            return classification

        except httpx.ConnectError:
            print("Warning: Cannot connect to Ollama. Defaulting to general.")
            return "general"
        except Exception as e:
            print(f"Error in classification: {e}")
            return "general"

    # ── get_structured_query ──────────────────────────────────────────────────

    async def get_structured_query(self, question: str, model_name: str = None, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        model_to_use = model_name if model_name else self.default_model
        print("Using Model:", model_to_use)

        domain = settings.get_domain()
        
        # Use actual DataFrame columns instead of hardcoded domain fields
        df = settings.get_dataframe()
        actual_columns = list(df.columns) if df is not None else domain.field_names
        base_prompt = get_query_planner_prompt(domain, actual_columns=actual_columns)

        context_section = ""
        if conversation_history:
            recent_history = conversation_history[-4:]
            context_lines  = [
                f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content'][:200]}"
                for msg in recent_history
            ]
            context_section = f"""
# Previous Conversation Context:
{chr(10).join(context_lines)}

# IMPORTANT: The current question may refer to entities or topics mentioned above.
# If the question uses pronouns (he, she, they, it) or partial names, resolve them using the context.

"""

        prompt = base_prompt + context_section + "\n\nUser Question:\n" + question

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={"model": model_to_use, "prompt": prompt, "stream": False, "format": "json"},
                )
                response.raise_for_status()

            data       = response.json()
            raw_output = data.get("response", "").strip()

            if not raw_output:
                return {"error": "Empty response from LLM", "query_type": "error"}

            try:
                return json.loads(raw_output)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", raw_output, re.DOTALL)
                if match:
                    return json.loads(match.group())
                return {"error": "Invalid JSON in LLM response", "query_type": "error"}

        except httpx.ConnectError:
            return {"error": "LLM service unavailable.", "query_type": "error"}
        except Exception as e:
            print(f"Error generating structured query: {e}")
            return {"error": str(e), "query_type": "error"}

    # ── generate_natural_response ─────────────────────────────────────────────

    async def generate_natural_response(self, question: str, result: Any, model_name: str = None) -> str:
        model_to_use = model_name if model_name else self.default_model
        print("Using Model", model_to_use)

        if result is None:
            formatted_result = "No data found"
        elif isinstance(result, dict) and "error" in result:
            formatted_result = f"Error - {result['error']}"
        elif isinstance(result, list):
            formatted_result = json.dumps(result, indent=2)
        elif isinstance(result, float):
            formatted_result = str(round(result, 2))
        else:
            formatted_result = str(result)

            print(f"[bypass_check] type={type(result).__name__} value={result}")  # ← ADD THIS

        # ── Aggregate bypass — skip LLM for single number results ─────────────
        numeric_val = None

        

        # Handle plain number (from _format_result single-cell return)
        if isinstance(result, (int, float)):
            numeric_val = result
        elif hasattr(result, 'item'):  # numpy scalar (np.float64, np.int64)
            numeric_val = result.item()

        # Handle list of dicts
        elif isinstance(result, list) and len(result) == 1:
            row = result[0]
            if isinstance(row, dict)  and len(row) == 1: 
                for v in row.values():
                    if isinstance(v, (int, float)) or hasattr(v, 'item'):
                        numeric_val = v.item() if hasattr(v, 'item') else v
                        break

        if numeric_val is not None:
            q = question.lower()
            if any(kw in q for kw in ["count", "how many", "total", "number of"]):
                return f"There are {int(numeric_val)} students in the database."
            elif any(kw in q for kw in ["average", "mean"]):
                return f"The average is {round(float(numeric_val), 2)}."
            elif any(kw in q for kw in ["highest", "maximum", "max"]):
                return f"The highest value is {numeric_val}."
            elif any(kw in q for kw in ["lowest", "minimum", "min"]):
                return f"The lowest value is {numeric_val}."
            else:
                return f"The result is {numeric_val}."
            

            
      
        # ─────────────────────────────────────────────────────────────────────

        if isinstance(result, list) and len(result) == 1:
            row = result[0]
            if isinstance(row, dict) and len(row) > 1:
                parts = [f"**{k.replace('_', ' ')}:** {v}"
                         for k, v in row.items()
                         if v not in (None, "", "nan")]
                return "\n".join(parts)

        domain = settings.get_domain()   # ← existing line, nothing changes below
        prompt = get_response_generator_prompt(domain, question, formatted_result)

        domain = settings.get_domain()
        prompt = get_response_generator_prompt(domain, question, formatted_result)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={"model": model_to_use, "prompt": prompt, "stream": False},
                )
                response.raise_for_status()

            data          = response.json()
            response_text = data.get("response", f"The result is: {result}").strip()

            for prefix in ["Response:", "Here's a response:", "Here's a friendly response:",
                           "The user asked", "It looks like", "The answer is:"]:
                if response_text.startswith(prefix):
                    response_text = response_text[len(prefix):].strip()

            if response_text.startswith('"') and response_text.endswith('"'):
                response_text = response_text[1:-1]

            if response_text.strip().startswith("{") or response_text.strip().startswith("["):
                try:
                    parsed = json.loads(response_text)
                    if isinstance(parsed, dict):
                        parts = [f"{k.replace('_', ' ')}: {v}" for k, v in parsed.items()
                                 if k not in ("Student_ID", "row") and v not in (None, "")]
                        response_text = "Here are the details — " + ", ".join(parts) + "."
                    elif isinstance(parsed, list):
                        response_text = f"Found {len(parsed)} record(s)."
                except Exception:
                    pass

            sentences = re.split(r'(?<=[.!?])\s+', response_text.strip())
            if len(sentences) > 2:
                response_text = " ".join(sentences[:2])

            if len(response_text) > 200:
                truncated  = response_text[:200]
                last_space = truncated.rfind(' ')
                response_text = truncated[:last_space] + "."

            return response_text

        except httpx.ConnectError:
            return "Sorry, the AI service is temporarily unavailable."
        except Exception as e:
            print(f"Error generating natural response: {e}")
            return "I encountered an error while processing your request."

    # ── generate_chat_response ────────────────────────────────────────────────

    async def generate_chat_response(
        self,
        question: str,
        model_name: str = None,
        conversation_history: List[Dict] = None,
    ) -> str:
        model_to_use = model_name if model_name else self.default_model

        if conversation_history:
            history_lines = []
            for msg in conversation_history[-6:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                history_lines.append(f"{role}: {msg['content'][:300]}")
            history_block = "\n".join(history_lines)
            prompt = (
                f"You are a helpful school management assistant.\n\n"
                f"Conversation so far:\n{history_block}\n\n"
                f"User: {question}\nAssistant:"
            )
        else:
            prompt = (
                f"You are a helpful school management assistant.\n\n"
                f"User: {question}\nAssistant:"
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={"model": model_to_use, "prompt": prompt, "stream": False},
                )
                response.raise_for_status()

            data = response.json()
            return data.get("response", "Hello! I'm here to help you.").strip()

        except httpx.ConnectError:
            return "Hello! I'm here to help, but the AI service is currently unavailable."
        except Exception as e:
            print(f"Error generating chat response: {e}")
            return "Hello! I'm experiencing some technical difficulties right now."

    # ── classify_rag_intent ───────────────────────────────────────────────────

    async def classify_rag_intent(self, question: str, model_name: str = None) -> dict:
        model_to_use = model_name if model_name else self.default_model

        prompt = f"""<|system|>
Classify the user question into ONE intent. Return ONLY valid JSON, nothing else.
<|end|>
<|user|>
Intents:
- "summarize" → user wants overview/summary of whole document
- "lookup"    → user wants specific fact, name, number, date
- "compare"   → user wants comparison between two or more things
- "list"      → user wants a list (benefits, features, drawbacks, uses)
- "explain"   → user wants concept explained in detail
- "general"   → anything else

Return ONLY this JSON:
{{"intent": "lookup", "retrieval_hint": "3-5 keywords to search", "top_k": 5}}

top_k rules: summarize=15, compare=10, list=6, explain=6, lookup=3, general=5

Question: {question}
<|end|>
<|assistant|>"""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={"model": model_to_use, "prompt": prompt, "stream": False, "format": "json"},
                )
                response.raise_for_status()
            data   = response.json()
            raw    = data.get("response", "{}").strip()
            result = json.loads(raw)
            hint = result.get("retrieval_hint", "").strip() or question
            return {
                "intent":         result.get("intent", "general"),
                "retrieval_hint": hint,
                "top_k":          int(result.get("top_k", 5)),
            }
        except Exception:
            return {"intent": "general", "retrieval_hint": question, "top_k": 5}

    # ── rag_answer ────────────────────────────────────────────────────────────

    async def rag_answer(self, question: str, chunks: List[Dict], model_name: str = None) -> str:
        model_to_use = model_name if model_name else self.default_model

        context_parts = []
        for i, chunk in enumerate(chunks, start=1):
            src  = chunk.get("filename", "unknown")
            meta = chunk.get("meta", {})
            if "page" in meta:
                loc = f"page {meta['page']}"
            elif "sheet" in meta and "row" in meta:
                loc = f"sheet '{meta['sheet']}', row {meta['row']}"
            elif "row" in meta:
                loc = f"row {meta['row']}"
            elif "element" in meta:
                loc = f"element '{meta['element']}'"
            else:
                loc = f"chunk {i}"
            context_parts.append(f"[Source {i}: {src} — {loc}]\n{chunk['text']}")

        context = "\n\n".join(context_parts)
        intent  = chunks[0].get("intent", "general") if chunks else "general"

        intent_prompts = {
            "summarize": f"""<|system|>
You are a strict document summarizer. Use ONLY the context below. Do NOT add outside knowledge.
Write a structured summary covering each major topic found in the context. Keep the summary under 200 words.
<|end|>
<|user|>
CONTEXT:
{context}
TASK: Summarize all major topics found in this document.
<|end|>
<|assistant|>""",
            "compare": f"""<|system|>
You are a strict document reader. Use ONLY the context below. Do NOT add outside knowledge.
If the comparison is not in the context, say: "This information is not found in the uploaded document."
<|end|>
<|user|>
CONTEXT:
{context}
QUESTION: {question}
<|end|>
<|assistant|>""",
            "list": f"""<|system|>
You are a strict document reader. Extract and list ONLY items explicitly mentioned in the context below.
Do NOT add outside knowledge. Use bullet points.
If not found say: "This information is not found in the uploaded document."
<|end|>
<|user|>
CONTEXT:
{context}
QUESTION: {question}
<|end|>
<|assistant|>""",
            "explain": f"""<|system|>
You are a strict document reader. Answer using ONLY the exact words and facts from the context below.
Do NOT add outside knowledge, definitions, or terms not present in the context.
Keep the answer under 150 words.
If something is not in the context, do not include it.
<|end|>
<|user|>
CONTEXT:
{context}
QUESTION: {question}
<|end|>
<|assistant|>""",
            "lookup": f"""<|system|>
You are a strict fact extractor. Extract the answer ONLY from the context below.
Do NOT add outside knowledge. Quote or closely paraphrase the relevant part.
If not found say: "This information is not found in the uploaded document."
<|end|>
<|user|>
CONTEXT:
{context}
QUESTION: {question}
<|end|>
<|assistant|>""",
            "general": f"""<|system|>
You are a strict document assistant. Answer using ONLY the context below.
Do NOT add outside knowledge. Do NOT guess or infer beyond what is written.
If not found say: "This information is not found in the uploaded document."
<|end|>
<|user|>
CONTEXT:
{context}
QUESTION: {question}
<|end|>
<|assistant|>""",
        }

        # Detect if source is structured data (Excel/CSV)
        is_structured = any(
            c.get("source_type") in ("excel", "csv")
            for c in chunks
        )

        # Override prompt for structured data lookups
        if is_structured:
            prompt = f"""<|system|>
You are a strict data reader. Copy values EXACTLY from the context below.
Do NOT modify, paraphrase, or replace any IDs, codes, or numbers.
List ALL fields found for the requested record, one per line as "Field: Value".
Do NOT add outside knowledge.
If not found say: "This information is not found in the uploaded document."
<|end|>
<|user|>
CONTEXT:
{context}
QUESTION: {question}
<|end|>
<|assistant|>"""
        else:
            prompt = intent_prompts.get(intent, intent_prompts["general"])

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={"model": model_to_use, "prompt": prompt, "stream": False},
                )
                response.raise_for_status()

            data   = response.json()
            answer = data.get("response", "Sorry, I couldn't generate a response.").strip()

        except httpx.ConnectError:
            return "Sorry, the AI service is temporarily unavailable."
        except Exception as e:
            print(f"Error generating RAG response: {e}")
            return "I encountered an error while processing your document-based question."

        for prefix in ["ANSWER:", "Answer:", "Response:"]:
            if answer.startswith(prefix):
                answer = answer[len(prefix):].strip()

        return answer


# Singleton instance
llm_service = LLMService()