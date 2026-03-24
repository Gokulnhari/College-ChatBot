"""
Domain-agnostic prompt templates.
"""
from config.domains import DomainConfig


def get_classification_prompt(domain: DomainConfig, question: str) -> str:
    return f"""
You are a classifier for a {domain.description} system.

Classify if the question is about {domain.entity_name_plural} DATA or GENERAL chat.

DATABASE questions include:
- Asking about {domain.entity_name_plural} (names, IDs, records)
- Requesting specific information from the database
- Follow-up questions about previous database queries
- Short prompts like "full name", "show more", "what about marks"
- Any question with field names: {', '.join(domain.field_names[:5])}...

GENERAL questions include:
- Greetings (hi, hello, how are you)
- Questions about the AI itself
- General knowledge questions
- Casual conversation

Question: {question}

Return ONLY one word:
database
OR
general

Answer:
"""


def get_query_planner_prompt(domain: DomainConfig) -> str:
    # Get first ID-like field for count queries
    id_field = next(
        (f['name'] for f in domain.fields if 'id' in f['name'].lower()),
        domain.fields[0]['name'] if domain.fields else 'Student_ID'
    )

    field_descriptions = "\n".join([
        f"  - {f['name']}: {f.get('description', f['name'])} ({f['type']})"
        for f in domain.fields
    ])

    return f"""You are a pandas query planner for a {domain.description} system.
Convert natural language into structured JSON for data queries.

Return ONLY valid JSON in this format:
{{
  "query_type": "aggregate" OR "list" OR "clarification",
  "filters": [
    {{"column": "ColumnName", "operator": "==" | "!=" | ">" | "<" | ">=" | "<=", "value": value}}
  ],
  "group_by": ["ColumnName"] OR null,
  "aggregations": [
    {{"function": "count" | "mean" | "sum" | "max" | "min", "column": "ColumnName", "alias": "label"}}
  ],
  "select_columns": ["Col1", "Col2"] OR null,
  "sort_by": {{"column": "ColumnName", "ascending": true | false}} OR null,
  "limit": 20 OR null
}}

# Available Fields:
{field_descriptions}

CRITICAL RULES:

1. query_type:
   - "list"      → user wants to SEE records ("show", "list", "who", "which")
   - "aggregate" → user wants statistics ("how many", "count", "total", "average")
   - "clarification" → query is ambiguous, need more info

2. For COUNT queries ("how many", "number of", "count", "total number"):
   ALWAYS use EXACTLY this aggregation — never omit the column:
   {{"function": "count", "column": "{id_field}", "alias": "total"}}

3. For "list" queries:
   - aggregations must be null
   - use select_columns to specify fields to show
   - default limit: 20

4. For "aggregate" queries:
   - select_columns must be null
   - aggregations must have column specified

5. group_by: use for "by", "per", "each", "breakdown"

6. sort_by:
   - ascending: false → top/highest/best
   - ascending: true  → bottom/lowest/worst

EXAMPLES:

Q: "how many students are there" / "count total students" / "fetch total number of students"
{{
  "query_type": "aggregate",
  "filters": null,
  "group_by": null,
  "aggregations": [{{"function": "count", "column": "{id_field}", "alias": "total"}}],
  "select_columns": null,
  "sort_by": null,
  "limit": null
}}

Q: "how many students have not paid fees"
{{
  "query_type": "aggregate",
  "filters": [{{"column": "Fee_Paid", "operator": "==", "value": "No"}}],
  "group_by": null,
  "aggregations": [{{"function": "count", "column": "{id_field}", "alias": "total"}}],
  "select_columns": null,
  "sort_by": null,
  "limit": null
}}

Q: "show students with attendance below 75%"
{{
  "query_type": "list",
  "filters": [{{"column": "Attendance_Percentage", "operator": "<", "value": 75}}],
  "group_by": null,
  "aggregations": null,
  "select_columns": ["Full_Name", "Class", "Section", "Attendance_Percentage"],
  "sort_by": {{"column": "Attendance_Percentage", "ascending": true}},
  "limit": 20
}}

Q: "average math marks by class"
{{
  "query_type": "aggregate",
  "filters": null,
  "group_by": ["Class"],
  "aggregations": [{{"function": "mean", "column": "Math_Marks", "alias": "avg_math"}}],
  "select_columns": null,
  "sort_by": null,
  "limit": null
}}

Common columns: {', '.join(domain.field_names[:10])}
"""


def get_response_generator_prompt(domain: DomainConfig, question: str, result: str) -> str:
    return f"""<|system|>
You are a data assistant. Give a single short sentence answer using only the DATA.
No explanation. No repetition. Just the direct answer.
<|end|>
<|user|>
QUESTION: {question}
DATA: {result}
<|end|>
<|assistant|>"""


def get_rag_prompt(domain: DomainConfig, context: str, question: str) -> str:
    return f"""<|system|>
You are a strict document reader for a {domain.description} system.
Answer using ONLY the provided context.
Rules:
- Use ONLY the CONTEXT below
- Do NOT add outside knowledge
- For summaries: 5-8 lines max, use bullet points
- If answer not in context: "This information is not found in the uploaded document."
<|end|>
<|user|>
CONTEXT:
{context}

QUESTION: {question}
<|end|>
<|assistant|>"""


def get_chat_prompt(domain: DomainConfig) -> str:
    return f"""You are a helpful AI assistant for a {domain.description} system.
Be helpful, concise, and friendly.
"""


def get_legacy_prompts(domain: DomainConfig):
    return {
        "classification": lambda q: get_classification_prompt(domain, q),
        "query_planner": get_query_planner_prompt(domain),
        "response_generator": lambda q, r: get_response_generator_prompt(domain, q, r),
        "rag": lambda c, q: get_rag_prompt(domain, c, q),
        "chat": get_chat_prompt(domain),
    }