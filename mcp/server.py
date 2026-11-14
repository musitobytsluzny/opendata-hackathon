try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP

from mcp.server.transport_security import TransportSecuritySettings

# Initialize central FastMCP server instance
mcp_server = FastMCP(
    name="KartogramMCP",
    instructions="Kartogram spatial data and presentation tools. Data tools require a user bearer token. Presentation tools return directives for a host that validates verified result references; they do not draw UI themselves.",
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
