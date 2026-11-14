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
        """Read indicative spatial checks, zoning plan (územní plán) and radon risk at known WGS84 coordinates; never guess coordinates."""
        return await _read(ctx, "/data/prevalidate/point", {"lat": lat, "lon": lon})

    @server.tool()
    async def prevalidate_parcel(
        cislo: str,
        ctx: Context,
        kod_ku: int | None = None,
        nazev_ku: str | None = None,
    ) -> dict:
        """Read indicative parcel checks, zoning plan (územní plán / funkční využití / zastavitelnost)
        and radon risk using parcel number (cislo, e.g. '841/1' or '969') and either cadastral-area code
        (kod_ku, e.g. 722618) or cadastral-area name (nazev_ku, e.g. 'Bolevec', 'Plzeň').
        """
        params: dict[str, str | int] = {"cislo": cislo}
        if kod_ku is not None:
            params["kod_ku"] = kod_ku
        if nazev_ku is not None:
            params["nazev_ku"] = nazev_ku
        return await _read(ctx, "/data/prevalidate/parcel", params)

    @server.tool()
    async def prevalidate_address(
        ctx: Context,
        adresa: str | None = None,
        cislo_popisne: int | None = None,
        cislo_orientacni: int | None = None,
        obec: str | None = None,
        ulice: str | None = None,
    ) -> dict:
        """Find parcel and read indicative spatial checks, zoning plan (územní plán) and radon risk
        based on address or house number (číslo popisné / orientační), street, and municipality
        (e.g. 'Bolevecká náves 1, Plzeň' or cislo_popisne=1, obec='Plzeň').
        """
        params: dict[str, str | int] = {}
        if adresa:
            params["adresa"] = adresa
        if cislo_popisne is not None:
            params["cislo_popisne"] = cislo_popisne
        if cislo_orientacni is not None:
            params["cislo_orientacni"] = cislo_orientacni
        if obec:
            params["obec"] = obec
        if ulice:
            params["ulice"] = ulice
        return await _read(ctx, "/data/prevalidate/address", params)

    @server.tool()
    async def search_amenities(
        query: str,
        ctx: Context,
        obec: str | None = None,
        kategorie: str | None = None,
    ) -> dict:
        """Search points of interest, facilities, schools, dormitories (domov mládeže),
        healthcare, transport, or amenities by name, category, or municipality.
        """
        params: dict[str, str] = {"query": query}
        if obec:
            params["obec"] = obec
        if kategorie:
            params["kategorie"] = kategorie
        return await _read(ctx, "/data/amenities", params)
