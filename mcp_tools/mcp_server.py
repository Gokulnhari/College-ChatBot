import sys
import os
import builtins

# Redirect all prints to stderr — stdout is reserved for MCP JSON-RPC
_orig_print = builtins.print
def _stderr_print(*args, **kwargs):
    kwargs["file"] = sys.stderr
    _orig_print(*args, **kwargs)
builtins.print = _stderr_print

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
import asyncio
import json

from config import settings
from vector_store import vector_store

app = Server("college-mcp-server")


# ── Register available tools ───────────────────────────────────────────────────
@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_record_count",
            description="Get total count of records, optionally filtered by class",
            inputSchema={
                "type": "object",
                "properties": {
                    "class_name": {
                        "type": "string",
                        "description": "Optional class name to filter by"
                    }
                },
                "required": []      # ← empty — class_name is optional
            }
        ),
        types.Tool(
            name="get_record_count",
            description="Get total count of records, optionally filtered by class",
            inputSchema={
                "type": "object",
                "properties": {
                    "class_name": {
                        "type": "string",
                        "description": "Optional class name to filter by"
                    }
                }
            }
        ),
        types.Tool(
            name="search_documents",
            description="Search indexed PDF or XML documents using RAG",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string"
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_column_names",
            description="Get all column names from the current loaded database",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
    ]


# ── Handle tool calls ──────────────────────────────────────────────────────────
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    if name == "query_database":
        df = settings.get_dataframe()
        if df is None:
            result = "No database loaded"
        else:
            filtered = df
            for col, val in (arguments.get("filters") or {}).items():
                if col in df.columns:
                    filtered = filtered[filtered[col] == val]
            result = filtered.to_json(orient="records")

    elif name == "get_record_count":
        df = settings.get_dataframe()
        if df is None:
            result = "No database loaded"
        else:
            class_name = arguments.get("class_name")
            # ← Fix: only filter if class_name is a non-empty string
            if class_name and isinstance(class_name, str) and class_name.strip() and "Class" in df.columns:
                df = df[df["Class"] == class_name]
            result = str(len(df))

    elif name == "search_documents":
        query  = arguments.get("query", "")
        chunks = vector_store.search(query, top_k=3)
        if not chunks:
            result = "No relevant documents found"
        else:
            result = "\n\n".join([
                f"[{c.get('filename', '?')}]: {c['text'][:300]}"
                for c in chunks
            ])

    elif name == "get_column_names":
        df = settings.get_dataframe()
        if df is None:
            result = "No database loaded"
        else:
            result = ", ".join(df.columns.tolist())

    else:
        result = f"Unknown tool: {name}"

    return [types.TextContent(type="text", text=result)]


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
    asyncio.run(main())