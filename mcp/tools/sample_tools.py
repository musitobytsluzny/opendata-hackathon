from typing import Any, Dict, List, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP

from services.api_client import get_api_client


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools with the FastMCP server."""

    @mcp.tool()
    async def search_datasets(
        query: str, category: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search open datasets on the Central API.

        Args:
            query: Search query keyword.
            category: Optional category filter.
            limit: Max results (1-100).
        """
        api = get_api_client()
        params = {"q": query, "limit": limit}
        if category:
            params["category"] = category

        try:
            results = await api.get("/datasets/search", params=params)
            return results if isinstance(results, list) else results.get("items", [results])
        except Exception as err:
            return [{"error": f"Failed to fetch datasets from Central API: {err}"}]

    @mcp.tool()
    async def execute_central_action(
        action_name: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Trigger an action endpoint on the Central API.

        Args:
            action_name: The action endpoint name.
            parameters: Action payload dictionary.
        """
        api = get_api_client()
        try:
            response = await api.post(f"/actions/{action_name}", json_data=parameters)
            return response
        except Exception as err:
            return {"status": "error", "message": f"Action execution failed: {err}"}
