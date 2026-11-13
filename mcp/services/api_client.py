from typing import Any, Dict, Optional
import httpx

from config import settings


class CentralAPIClient:
    """Async HTTP client wrapper for communicating with Central API."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = base_url or settings.CENTRAL_API_BASE_URL
        self.api_key = api_key or settings.CENTRAL_API_KEY
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Initialize the underlying httpx AsyncClient session."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=settings.CENTRAL_API_TIMEOUT,
        )

    async def close(self) -> None:
        """Close the AsyncClient session."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("CentralAPIClient is not initialized. Call 'start()' during app lifespan.")
        return self._client

    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Send a GET request to Central API."""
        response = await self.client.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()

    async def post(self, endpoint: str, json_data: Optional[Dict[str, Any]] = None) -> Any:
        """Send a POST request to Central API."""
        response = await self.client.post(endpoint, json=json_data)
        response.raise_for_status()
        return response.json()


# Global client instance to be managed by FastAPI lifespan
_api_client_instance: Optional[CentralAPIClient] = None


def get_api_client() -> CentralAPIClient:
    """Dependency / accessor for active CentralAPIClient instance."""
    global _api_client_instance
    if _api_client_instance is None:
        _api_client_instance = CentralAPIClient()
    return _api_client_instance
