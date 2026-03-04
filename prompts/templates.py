"""
Domain-agnostic prompt templates.
Uses domain configuration to generate appropriate prompts for any industry.
"""
from config.domains import DomainConfig


def get_classification_prompt(domain: DomainConfig, question: str) -> str:
    """
    Generate question classification prompt for any domain.

    Returns: Prompt to classify if question is database-related or general chat
    """
    return f"""
You are a classifier for a {domain.description} system.

Classify if the question is about {domain.entity_name_plural} DATA or GENERAL chat.

DATABASE questions include:
- Asking about {domain.entity_name_plural} (names, IDs, records)
- Requesting specific information from the database
- Follow-up questions about previous database queries
- Short prompts like "full name", "show more", "what about marks" (these are follow-ups to previous database questions)
- Any question with field names: {', '.join(domain.field_names[:5])}...

GENERAL questions include:
- Greetings (hi, hello, how are you)
- Questions about the AI itself
- General knowledge questions
- Casual conversation

IMPORTANT: If the question seems like a follow-up or continuation (short phrases, pronouns, "more", "show", etc.),
classify as DATABASE - it's likely continuing a previous database query.

Question: {question}

Return ONLY one word:
database
OR
general

Answer:
"""


def get_query_planner_prompt(domain: DomainConfig) -> str:
    """
    Generate structured query planning prompt for any domain.

    Returns: Prompt template for converting natural language to structured queries
    """
    # Build field list with descriptions
    field_descriptions = "\n".join([
        f"  - {f['name']}: {f.get('description', f['name'])} ({f['type']})"
        for f in domain.fields
    ])

    # Build example queries
    examples_text = "\n".join([f"- {q}" for q in domain.example_queries[:3]])

    return f"""You are a query planner for a {domain.description} system.

Convert natural language questions into structured queries that can be executed on a pandas DataFrame.

# Available Fields:
{field_descriptions}

# Query Types:
1. **filter**: Return {domain.entity_name_plural} matching criteria
2. **aggregate**: Calculate statistics (mean, sum, count, max, min)
3. **sort**: Order {domain.entity_name_plural} by a field
4. **clarification**: Ask user for more information when ambiguous

# Output Format (JSON):
{{
  "query_type": "filter" | "aggregate" | "sort" | "clarification",
  "filters": [
    {{"field": "Field_Name", "operator": "==" | "!=" | ">" | "<" | ">=" | "<=" | "contains", "value": "value"}}
  ],
  "aggregation": {{
    "function": "mean" | "sum" | "count" | "max" | "min",
    "column": "Field_Name",
    "group_by": "Field_Name (optional)"
  }},
  "sort": {{
    "column": "Field_Name",
    "ascending": true | false
  }},
  "limit": 10,
  "question": "For clarification type: question to ask user",
  "options": []  // For clarification: possible options
}}

# Examples of typical queries:
{examples_text}

# Rules:
- Use exact field names from Available Fields
- For text fields with PARTIAL names, use "contains" operator (case-insensitive)
  Example: {{"field": "Full_Name", "operator": "contains", "value": "meera"}}
- For exact text matching, use "==" operator (case-insensitive)
- For numeric comparisons, use appropriate operators (>, <, >=, <=)
- If {domain.entity_name} name is ambiguous, use clarification type
- Limit results to reasonable numbers (default 20)
- Return ONLY valid JSON, no additional text

# Special Cases:
- "top N" queries → sort type with limit
- "average/mean" → aggregate with function: mean
- "total/sum" → aggregate with function: sum
- "how many/count" → aggregate with function: count
- Multiple conditions → multiple filters
- Name searches (e.g., "who is meera", "find john") → use "contains" operator on name field
  Example: {{"field": "Full_Name", "operator": "contains", "value": "meera"}}
"""


def get_response_generator_prompt(domain: DomainConfig, question: str, result: str) -> str:
    """
    Generate natural language response formatting prompt.

    Args:
        domain: Domain configuration
        question: User's original question
        result: Query execution result (pandas output)

    Returns: Prompt for converting structured result to natural language
    """
    return f"""You are a helpful assistant for a {domain.description} system.

Convert the query result into a natural, conversational response.

User Question: {question}

Query Result:
{result}

# Instructions:
- Provide a clear, direct answer to the user's question
- Use natural language, avoid technical jargon
- If result is a number, include appropriate units/context
- If result is a list, format it readably (bullets or numbered)
- If result is empty/None, say "No {domain.entity_name_plural} found matching that criteria"
- Be concise but friendly
- Don't mention "DataFrame", "query", or technical terms
- Don't add preambles like "Based on the data..." - just answer directly

Response:
"""


def get_rag_prompt(domain: DomainConfig, context: str, question: str) -> str:
    """
    Generate RAG (Retrieval-Augmented Generation) prompt for document Q&A.

    Args:
        domain: Domain configuration
        context: Retrieved document chunks
        question: User's question

    Returns: Prompt for answering using document context
    """
    return f"""<|system|>
You are a strict document reader for a {domain.description} system.
You must answer using ONLY the text provided in the CONTEXT section.
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
- Use ONLY the context above
- Do NOT add your own knowledge about {domain.entity_name_plural} or {domain.name}
- Do NOT make assumptions
- Answer directly without preamble
- If multiple {domain.entity_name_plural} are mentioned, be specific about each one
<|end|>

<|assistant|>"""


def get_chat_prompt(domain: DomainConfig) -> str:
    """
    Generate general chat system prompt.

    Returns: Prompt for handling general (non-database) questions
    """
    return f"""You are a helpful AI assistant for a {domain.description} system.

You can:
1. Answer questions about {domain.entity_name_plural} in the database
2. Have casual conversations
3. Provide general information

You have access to a database containing {domain.entity_name} records with the following information:
{', '.join([f['name'] for f in domain.fields[:5]])}{'...' if len(domain.fields) > 5 else ''}

Be helpful, concise, and friendly.
"""


# ============================================================================
# Backward Compatibility - For systems still using old format
# ============================================================================

def get_legacy_prompts(domain: DomainConfig):
    """
    Generate all prompts at once (for backward compatibility).

    Returns: Dict with all prompt types
    """
    return {
        "classification": lambda q: get_classification_prompt(domain, q),
        "query_planner": get_query_planner_prompt(domain),
        "response_generator": lambda q, r: get_response_generator_prompt(domain, q, r),
        "rag": lambda c, q: get_rag_prompt(domain, c, q),
        "chat": get_chat_prompt(domain),
    }
