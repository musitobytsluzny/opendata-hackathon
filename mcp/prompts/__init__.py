try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP

from .sample_prompts import register_prompts as register_sample_prompts


def register_all_prompts(mcp: FastMCP) -> None:
    """Register all prompt modules into FastMCP."""
    register_sample_prompts(mcp)


__all__ = ["register_all_prompts"]
