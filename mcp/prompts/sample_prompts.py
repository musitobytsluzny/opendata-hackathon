try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP


def register_prompts(mcp: FastMCP) -> None:
    """Register prompt templates with FastMCP server."""

    @mcp.prompt()
    def summarize_dataset(dataset_name: str, focus_area: str = "general") -> str:
        """Prompt template for requesting dataset analysis/summary."""
        return (
            f"Please analyze the open dataset '{dataset_name}' with focus on '{focus_area}'. "
            f"Provide key insights, potential data anomalies, and useful applications."
        )
