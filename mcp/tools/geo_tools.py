"""Authenticated read-only tools. Each request forwards its own user token."""

import httpx
from mcp.server.fastmcp import Context, FastMCP
from services.api_client import get_api_client


async def _read(ctx: Context, path: str, params=None) -> dict:
    request = ctx.request_context.request
    authorization = request.headers.get("authorization", "") if request else ""
    if not authorization.lower().startswith("bearer "):
        return {"error": "Přihlášení je vyžadované.", "status": 401}
    try:
        response = await get_api_client().client.get(
            path, params=params, headers={"Authorization": authorization}
        )
        if response.is_error:
            return {"error": "Datový dotaz se nepodařil.", "status": response.status_code}
        return response.json()
    except httpx.HTTPError:
        return {"error": "Datová služba je nedostupná.", "status": 503}


def register_geo_tools(server: FastMCP):
    @server.tool()
    async def dataset_catalog(ctx: Context) -> dict:
        """List actually loaded local datasets, row counts and demo/external provenance."""
        return await _read(ctx, "/data/catalog")

    @server.tool()
    async def district_statistics(metric: str, ctx: Context) -> dict:
        """Read district aggregates for available municipalities. Metrics: population,
        seniors_pct, children_pct, greenery_pct, ndvi. Never infer absent districts as zero.
        """
        return await _read(ctx, "/data/statistics", {"metric": metric})

    @server.tool()
    async def prevalidate_point(lat: float, lon: float, ctx: Context) -> dict:
        """Read indicative spatial checks at known WGS84 coordinates; never guess coordinates."""
        return await _read(ctx, "/data/prevalidate/point", {"lat": lat, "lon": lon})

    @server.tool()
    async def prevalidate_parcel(kod_ku: int, cislo: str, ctx: Context) -> dict:
        """Read indicative parcel checks using cadastral-area code and parcel number, e.g. 1234/2."""
        return await _read(ctx, "/data/prevalidate/parcel", {"kod_ku": kod_ku, "cislo": cislo})
