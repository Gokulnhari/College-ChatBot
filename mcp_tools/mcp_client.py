import sys
import os
from typing import List, Dict, Any


class MCPClient:
    def __init__(self):
        self.session    = None
        self.tools      = []
        self._connected = False

    async def connect(self):
        try:
            from mcp import ClientSession
            from mcp.client.stdio import StdioServerParameters, stdio_client

            server_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "mcp_server.py"
            )

            server_params = StdioServerParameters(
                command=sys.executable,
                args=[server_path],
            )

            self._client            = stdio_client(server_params)
            self._read, self._write = await self._client.__aenter__()
            self.session            = ClientSession(self._read, self._write)
            await self.session.__aenter__()
            await self.session.initialize()
            tools_result    = await self.session.list_tools()
            self.tools      = tools_result.tools
            self._connected = True
            print(f"[MCP] Connected. Tools: {[t.name for t in self.tools]}")

        except Exception as e:
            print(f"[MCP] Connection failed: {e}")
            self._connected = False

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call an MCP tool by name"""
        if not self._connected:
            return "MCP not connected"
        try:
            result = await self.session.call_tool(tool_name, arguments)
            return result.content[0].text
        except Exception as e:
            return f"Tool error: {e}"

    def get_tools_for_ollama(self) -> List[Dict]:
        """Format MCP tools for Ollama tool_use format"""
        return [
            {
                "type": "function",
                "function": {
                    "name":        t.name,
                    "description": t.description,
                    "parameters":  t.inputSchema,
                }
            }
            for t in self.tools
        ]

    @property
    def is_connected(self) -> bool:
        return self._connected


# Singleton
mcp_client = MCPClient()