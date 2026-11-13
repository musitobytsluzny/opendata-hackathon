try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP

from mcp.server.transport_security import TransportSecuritySettings

# Initialize central FastMCP server instance
mcp_server = FastMCP(
    name="OpenData MCP Server",
    instructions="MCP Server connecting to OpenData Central API to provide datasets, tools, and resources.",
    transport_security=TransportSecuritySettings(
        allowed_hosts=[
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
            "mcp",
            "mcp:*",
            "[::1]",
            "[::1]:*",
        ],
        allowed_origins=[
            "http://localhost",
            "http://localhost:*",
            "http://127.0.0.1",
            "http://127.0.0.1:*",
        ],
    ),
)
