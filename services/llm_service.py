"""
LLM service for making API calls to Ollama.
Handles all interactions with the language model.

# ============================================================
# CHANGES FROM ORIGINAL — llm_service.py
# ─────────────────────────────────────────────────────────────
# ADDED: rag_answer()   → answers a question given retrieved chunks
# Everything else (classify_question, get_structured_query,
# generate_natural_response, generate_chat_response) is UNCHANGED.
# ============================================================
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


class LLMService:
    """Service for interacting with the LLM"""

    def __init__(self):
        self.url          = settings.OLLAMA_URL
        self.timeout      = httpx.Timeout(settings.OLLAMA_TIMEOUT)
        self.default_model = settings.DEFAULT_MODEL

    # ── UNCHANGED: classify_question ──────────────────────────────────────────

    async def classify_question(self, question: str, model_name: str = None) -> str:
        """
        Classify whether question is database-related or general chat.
        Returns: 'database' or 'general'
        """
        model_to_use = model_name if model_name else self.default_model

        prompt = f"""
        You are a classifier.

        If the user question is related to student data, marks, class, section, student name,
        return ONLY this word:
        database

        If the question is casual conversation, greeting, or general knowledge,
        return ONLY this word:
        general

        Question: {question}
        Answer:
        """

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={"model": model_to_use, "prompt": prompt, "stream": False}
                )
                response.raise_for_status()

            data   = response.json()
            result = data.get("response", "").strip().lower()

            return "database" if "database" in result else "general"
            
        except httpx.ConnectError:
            # Default to general if Ollama is not available
            print("Warning: Cannot connect to Ollama service. Defaulting to general classification.")
            return "general"
        except Exception as e:
            print(f"Error in question classification: {e}")
            return "general"

    # ── UNCHANGED: get_structured_query ───────────────────────────────────────

    async def get_structured_query(self, question: str, model_name: str = None) -> Dict[str, Any]:
        model_to_use = model_name if model_name else self.default_model
        print("Using Model:", model_to_use)

        prompt = QUERY_PLANNER_PROMPT + "\nUser Question:\n" + question

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={
                        "model":  model_to_use,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    },
                )
                response.raise_for_status()

            data = response.json()

            if "response" not in data:
                return {"error": "Invalid LLM response", "query_type": "error"}

            raw_output = data["response"].strip()

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
            print("Error: Cannot connect to Ollama service.")
            return {"error": "LLM service unavailable. Please make sure Ollama is running.", "query_type": "error"}
        except Exception as e:
            print(f"Error generating structured query: {e}")
            return {"error": str(e), "query_type": "error"}

    # ── UNCHANGED: generate_natural_response ──────────────────────────────────

    async def generate_natural_response(
        self, question: str, result: Any, model_name: str = None
    ) -> str:
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

        prompt = RESPONSE_GENERATOR_PROMPT.format(
            question=question,
            result=formatted_result
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={"model": model_to_use, "prompt": prompt, "stream": False},
                )
                response.raise_for_status()
                
            data = response.json()

            if "response" not in data:
                return f"The result is: {result}"

            response_text = data["response"].strip()

            prefixes_to_remove = [
                "Response:", "Here's a response:", "Here's a friendly response:",
                "The user asked", "It looks like",
            ]
            for prefix in prefixes_to_remove:
                if response_text.startswith(prefix):
                    response_text = response_text[len(prefix):].strip()

            if response_text.startswith('"') and response_text.endswith('"'):
                response_text = response_text[1:-1]

            return response_text
            
        except httpx.ConnectError:
            return "Sorry, the AI service is temporarily unavailable. Please make sure Ollama is running on your system."
        except Exception as e:
            print(f"Error generating natural response: {e}")
            return "I encountered an error while processing your request."

    # ── UNCHANGED: generate_chat_response ─────────────────────────────────────

    async def generate_chat_response(self, question: str, model_name: str = None) -> str:
        """Handle general chat questions (non-database related)."""
        model_to_use = model_name if model_name else self.default_model
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={"model": model_to_use, "prompt": question, "stream": False},
                )
                response.raise_for_status()
                
            data = response.json()

            if "response" not in data:
                return "Hello! I'm here to help you."

            return data["response"].strip()
            
        except httpx.ConnectError:
            return "Hello! I'm here to help, but the AI service is currently unavailable. Please make sure Ollama is running."
        except Exception as e:
            print(f"Error generating chat response: {e}")
            return "Hello! I'm experiencing some technical difficulties right now."

    # ── RAG ADDITION: rag_answer ───────────────────────────────────────────────

    async def rag_answer(
        self,
        question: str,
        chunks: List[Dict],
        model_name: str = None,
    ) -> str:
        """
        # RAG ADDITION
        Answer a question using retrieved document chunks as context.

        Args:
            question: User's question
            chunks:   List of dicts from vector_store.search()
                      Each has keys: text, filename, source_type, score, meta
            model_name: Ollama model to use

        Returns:
            Natural language answer grounded in the provided context.
        """
        model_to_use = model_name if model_name else self.default_model

        # Build context block from retrieved chunks
        context_parts = []
        for i, chunk in enumerate(chunks, start=1):
            src = chunk.get("filename", "unknown")
            meta = chunk.get("meta", {})

            # Friendly location label (page / row / sheet / element)
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

            context_parts.append(
                f"[Source {i}: {src} — {loc}]\n{chunk['text']}"
            )

        context = "\n\n".join(context_parts)



        prompt = f"""<|system|>
You are a strict document reader. You must answer using ONLY the text provided in the CONTEXT section.
You are FORBIDDEN from using any outside knowledge.
If the answer exists in the context, extract it word-for-word or paraphrase it closely.
If the answer does not exist in the context, respond only with: "This information is not found in the uploaded document."
Never mention GPT, OpenAI, Microsoft, or any information not present in the context.
<|end|>
<|user|>
CONTEXT:
{context}

QUESTION: {question}

Rules:
- Use ONLY the context above.
- Do NOT add your own knowledge.
- Do NOT make assumptions.
- Answer directly without preamble.
<|end|>
<|assistant|>"""



        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={"model": model_to_use, "prompt": prompt, "stream": False},
                )
                response.raise_for_status()

            data = response.json()
            if "response" not in data:
                return "Sorry, I couldn't generate a response from the documents."

            answer = data["response"].strip()
            
        except httpx.ConnectError:
            return "Sorry, the AI service is temporarily unavailable. Please make sure Ollama is running on your system to get responses from uploaded documents."
        except Exception as e:
            print(f"Error generating RAG response: {e}")
            return "I encountered an error while processing your document-based question."

        # Strip common preamble the model might add
        for prefix in ["ANSWER:", "Answer:", "Response:"]:
            if answer.startswith(prefix):
                answer = answer[len(prefix):].strip()

        return answer


# Create singleton instance
llm_service = LLMService()