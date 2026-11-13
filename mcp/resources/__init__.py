try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP

from .sample_resources import register_resources as register_sample_resources


def register_all_resources(mcp: FastMCP) -> None:
    """Register all resource modules into FastMCP."""
    register_sample_resources(mcp)


__all__ = ["register_all_resources"]
