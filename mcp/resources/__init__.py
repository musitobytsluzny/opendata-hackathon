try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP


def register_all_resources(mcp: FastMCP) -> None:
    """No public placeholder resources: real data is accessed through authenticated tools."""


__all__ = ["register_all_resources"]
