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
from prompts.templates import (
    get_classification_prompt,
    get_query_planner_prompt,
    get_response_generator_prompt,
    get_rag_prompt
)


class LLMService:
    """Service for interacting with the LLM"""

    def __init__(self):
        self.url          = settings.OLLAMA_URL
        self.timeout      = httpx.Timeout(settings.OLLAMA_TIMEOUT)
        self.default_model = settings.DEFAULT_MODEL

    # ── UNCHANGED: classify_question ──────────────────────────────────────────

    async def classify_question(self, question: str, model_name: str = None, conversation_history: List[Dict] = None) -> str:
        """
        Classify whether question is database-related or general chat.
        Returns: 'database' or 'general'

        Args:
            question: Current user question
            model_name: Model to use
            conversation_history: Previous conversation turns for context
        """
        # HEURISTIC: Short follow-up questions with conversation history → database
        # Examples: "full name", "show more", "what about marks", "his class"
        if conversation_history and len(conversation_history) > 0:
            question_lower = question.lower().strip()
            # Check if it's a very short question (likely a follow-up)
            word_count = len(question_lower.split())

            # Short questions (1-3 words) with history are almost always follow-ups
            if word_count <= 3:
                # Check if previous conversation was about database
                last_user_msg = next((msg for msg in reversed(conversation_history) if msg['role'] == 'user'), None)
                if last_user_msg:
                    # If the last question was likely database-related, this is too
                    domain = settings.get_domain()
                    entity_mentioned = any(entity in last_user_msg['content'].lower()
                                         for entity in [domain.entity_name, domain.entity_name_plural])
                    field_mentioned = any(field.lower() in last_user_msg['content'].lower()
                                        for field in domain.field_names[:10])

                    if entity_mentioned or field_mentioned:
                        print(f"[classify] Short follow-up detected: '{question}' → database")
                        return "database"

        model_to_use = model_name if model_name else self.default_model

        # Use domain-aware classification prompt
        domain = settings.get_domain()
        base_prompt = get_classification_prompt(domain, question)

        # Add conversation context if available
        if conversation_history:
            context_str = "\n".join([
                f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content'][:200]}"
                for msg in conversation_history[-3:]  # Last 3 turns for context
            ])
            prompt = f"""Previous conversation:
{context_str}

{base_prompt}"""
        else:
            prompt = base_prompt

        print(f"[classify] Classifying: '{question}' (history: {len(conversation_history or [])} turns)")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json={"model": model_to_use, "prompt": prompt, "stream": False}
                )
                response.raise_for_status()

            data   = response.json()
            result = data.get("response", "").strip().lower()

            classification = "database" if "database" in result else "general"
            print(f"[classify] Result: {classification} (LLM output: '{result[:50]}')")
            return classification
            
        except httpx.ConnectError:
            # Default to general if Ollama is not available
            print("Warning: Cannot connect to Ollama service. Defaulting to general classification.")
            return "general"
        except Exception as e:
            print(f"Error in question classification: {e}")
            return "general"

    # ── UNCHANGED: get_structured_query ───────────────────────────────────────

    async def get_structured_query(self, question: str, model_name: str = None, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        Generate structured query from natural language.

        Args:
            question: Current user question
            model_name: Model to use
            conversation_history: Previous conversation for context resolution
        """
        model_to_use = model_name if model_name else self.default_model
        print("Using Model:", model_to_use)

        # Use domain-aware query planner prompt
        domain = settings.get_domain()
        base_prompt = get_query_planner_prompt(domain)

        # Add conversation context for follow-up questions
        context_section = ""
        if conversation_history:
            recent_history = conversation_history[-4:]  # Last 4 turns
            context_lines = []
            for msg in recent_history:
                role = "User" if msg['role'] == 'user' else "Assistant"
                context_lines.append(f"{role}: {msg['content'][:200]}")  # Truncate long messages

            context_section = f"""
# Previous Conversation Context:
{chr(10).join(context_lines)}

# IMPORTANT: The current question may refer to entities or topics mentioned above.
# If the question uses pronouns (he, she, they, it) or partial names, resolve them using the context.
# For example:
# - "Full name" after asking about "Meera" → asking for Meera's full name
# - "What about marks?" after discussing a student → asking about that student's marks
# - "Show me more" → continue previous query

"""

        prompt = base_prompt + context_section + "\n\nUser Question:\n" + question

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

        # Use domain-aware response generator prompt
        domain = settings.get_domain()
        prompt = get_response_generator_prompt(domain, question, formatted_result)

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

        # Use domain-aware RAG prompt
        domain = settings.get_domain()
        prompt = get_rag_prompt(domain, context, question)



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