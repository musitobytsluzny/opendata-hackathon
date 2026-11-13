try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP

from .sample_tools import register_tools as register_sample_tools


def register_all_tools(mcp: FastMCP) -> None:
    """Register all tool modules into FastMCP."""
    register_sample_tools(mcp)


__all__ = ["register_all_tools"]
