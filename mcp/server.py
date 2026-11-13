try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP

# Initialize central FastMCP server instance
mcp_server = FastMCP(
    name="OpenData MCP Server",
    instructions="MCP Server connecting to OpenData Central API to provide datasets, tools, and resources."
)
