print("LOADED FILE:", __file__)

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


def get_query_planner_prompt(domain: DomainConfig, actual_columns: list = None, df=None) -> str:
    print("UPDATED FUNCTION CALLED")

    # ── Determine id_field and columns ────────────────────────────────────────
    if actual_columns:
        id_field = next(
            (c for c in actual_columns if "id" in c.lower()),
            actual_columns[0] if actual_columns else "Student_ID"
        )
        columns_str = ", ".join(actual_columns)
    else:
        id_field = next(
            (f['name'] for f in domain.fields if 'id' in f['name'].lower()),
            domain.fields[0]['name'] if domain.fields else 'Student_ID'
        )
        columns_str = ", ".join(domain.field_names[:10])
        actual_columns = domain.field_names

    # ── Build column info with sample values ──────────────────────────────────
    field_descriptions = ""
    if df is not None:
        for col in actual_columns:
            if col not in df.columns:
                continue
            dtype = str(df[col].dtype)
            if df[col].dtype == object:
                unique_vals = df[col].dropna().unique().tolist()
                if len(unique_vals) > 20:
                    field_descriptions += f"  - {col} (text)\n"
                else:
                    # ← reduce to max 6 values
                    sample = ", ".join(f'"{v}"' for v in unique_vals[:6])
                    field_descriptions += f"  - {col}: {sample}\n"
            elif "int" in dtype or "float" in dtype:
                mn = round(float(df[col].min()), 2)
                mx = round(float(df[col].max()), 2)
                field_descriptions += f"  - {col}: {mn} to {mx}\n"

        # ← reduce cap from 1500 to 800
        if len(field_descriptions) > 800:
            field_descriptions = field_descriptions[:800] + "\n..."
    else:
        # Fallback to domain field descriptions
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

# COLUMNS AND THEIR VALUES IN THE CURRENT DATABASE:
{field_descriptions}

CRITICAL RULES:

1. query_type:
   - "list"      → user wants to SEE records ("show", "list", "who", "fetch", "get", "find")
   - "aggregate" → user wants statistics ("how many", "count", "total", "average")
   - "clarification" → query is ambiguous

2. FILTERS — match user's words to the sample values above and use EXACT values:
   - For location/city queries like "in Bangalore" → filter on City column
   - For branch/department queries like "CSE students" → filter on Branch/Department column
   - For grade queries like "students with A grade" → filter on Grade column
   - For numeric ranges like "above 80" or "below 75" → use >, <, >=, <= operators
   - NEVER use group_by for these — always use filters

3. group_by: ONLY use for "group by", "per each", "breakdown by" — NEVER for location/category filters

4. For COUNT queries ("how many", "number of", "count", "total"):
   {{"function": "count", "column": "{id_field}", "alias": "total"}}

5. For "list" queries:
   - aggregations must be null
   - select_columns: null returns all columns (preferred for "full details")
   - default limit: 20

6. For "aggregate" queries:
   - select_columns must be null

7. sort_by:
   - ascending: false → top/highest/best
   - ascending: true  → bottom/lowest/worst

EXAMPLES:

Q: "list students from Bangalore" / "students in Mumbai"
{{
  "query_type": "list",
  "filters": [{{"column": "City", "operator": "==", "value": "Bangalore"}}],
  "group_by": null,
  "aggregations": null,
  "select_columns": null,
  "sort_by": null,
  "limit": 20
}}

Q: "show CSE branch students" / "list IT department students"
{{
  "query_type": "list",
  "filters": [{{"column": "Branch", "operator": "==", "value": "CSE"}}],
  "group_by": null,
  "aggregations": null,
  "select_columns": null,
  "sort_by": null,
  "limit": 20
}}

Q: "top 5 students by average marks"
{{
  "query_type": "list",
  "filters": null,
  "group_by": null,
  "aggregations": null,
  "select_columns": null,
  "sort_by": {{"column": "Average", "ascending": false}},
  "limit": 5
}}

Q: "students with attendance below 75"
{{
  "query_type": "list",
  "filters": [{{"column": "Attendance_Percentage", "operator": "<", "value": 75}}],
  "group_by": null,
  "aggregations": null,
  "select_columns": null,
  "sort_by": {{"column": "Attendance_Percentage", "ascending": true}},
  "limit": 20
}}

Q: "how many students are there"
{{
  "query_type": "aggregate",
  "filters": null,
  "group_by": null,
  "aggregations": [{{"function": "count", "column": "{id_field}", "alias": "total"}}],
  "select_columns": null,
  "sort_by": null,
  "limit": null
}}

Q: "average marks by branch"
{{
  "query_type": "aggregate",
  "filters": null,
  "group_by": ["Branch"],
  "aggregations": [{{"function": "mean", "column": "Average", "alias": "avg_marks"}}],
  "select_columns": null,
  "sort_by": null,
  "limit": null
}}

Q: "students with grade A+ in CSE"
{{
  "query_type": "list",
  "filters": [
    {{"column": "Grade", "operator": "==", "value": "A+"}},
    {{"column": "Branch", "operator": "==", "value": "CSE"}}
  ],
  "group_by": null,
  "aggregations": null,
  "select_columns": null,
  "sort_by": null,
  "limit": 20
}}

Available columns: {columns_str}
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