from typing import Any, Dict
try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP

from services.api_client import get_api_client


def register_resources(mcp: FastMCP) -> None:
    """Register all MCP resources with the FastMCP server."""

    @mcp.resource("central-api://status")
    async def get_central_api_status() -> str:
        """Read system status feed from Central API."""
        api = get_api_client()
        try:
            status_data = await api.get("/status")
            return f"Central API Status: {status_data}"
        except Exception as err:
            return f"Unable to retrieve Central API status: {err}"

    @mcp.resource("central-api://datasets/{dataset_id}")
    async def get_dataset_details(dataset_id: str) -> str:
        """Fetch details for a specific dataset from Central API."""
        api = get_api_client()
        try:
            dataset = await api.get(f"/datasets/{dataset_id}")
            return str(dataset)
        except Exception as err:
            return f"Error fetching dataset '{dataset_id}': {err}"
