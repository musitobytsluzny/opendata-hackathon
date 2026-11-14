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
    async def prevalidate_parcel(
        cislo: str,
        kod_ku: int | None = None,
        nazev_ku: str | None = None,
        ctx: Context = None,
    ) -> dict:
        """Read indicative parcel checks using parcel number (cislo, e.g. '841/1' or '969')
        and either cadastral-area code (kod_ku, e.g. 722618) or cadastral-area name
        (nazev_ku, e.g. 'Bolevec', 'Plzeň').
        """
        params = {"cislo": cislo}
        if kod_ku is not None:
            params["kod_ku"] = kod_ku
        if nazev_ku is not None:
            params["nazev_ku"] = nazev_ku
        return await _read(ctx, "/data/prevalidate/parcel", params)

    @server.tool()
    async def prevalidate_address(
        adresa: str | None = None,
        cislo_popisne: int | None = None,
        cislo_orientacni: int | None = None,
        obec: str | None = None,
        ulice: str | None = None,
        ctx: Context = None,
    ) -> dict:
        """Find parcel and read indicative spatial checks based on address or house number
        (číslo popisné / orientační), street, and municipality (e.g. 'Bolevecká náves 1, Plzeň'
        or cislo_popisne=1, obec='Plzeň').
        """
        params = {}
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
        obec: str | None = None,
        kategorie: str | None = None,
        ctx: Context = None,
    ) -> dict:
        """Search points of interest, facilities, schools, dormitories (domov mládeže),
        healthcare, transport, or amenities by name, category, or municipality.
        """
        params = {"query": query}
        if obec:
            params["obec"] = obec
        if kategorie:
            params["kategorie"] = kategorie
        return await _read(ctx, "/data/amenities", params)

    @server.tool()
    async def search_places(
        query: str, kind: str = "obec", limit: int = 10, ctx: Context = None
    ) -> dict:
        """Resolve real stored place IDs before spatial operations. kind: obec (municipality),
        ku (cadastral area), poi (amenity), parcela. Preserve ambiguity; never invent IDs or coordinates.
        """
        return await _read(
            ctx, "/data/places/search", {"query": query, "kind": kind, "limit": limit}
        )

    @server.tool()
    async def place_geometry(place_id: str, ctx: Context) -> dict:
        """Get the actual boundary/point of a resolved place ID for map display."""
        return await _read(ctx, "/data/places/geometry", {"place_id": place_id})

    @server.tool()
    async def municipality_statistics(
        metric: str,
        district: str | None = None,
        limit: int = 20,
        descending: bool = True,
        ctx: Context = None,
    ) -> dict:
        """Rank individual municipalities by a loaded metric (population, seniors_pct,
        children_pct, greenery_pct, ndvi). Optional exact Czech district name; limit <=50.
        Returns verified rows suitable for tables, charts and map points.
        """
        params = {"metric": metric, "limit": limit, "descending": descending}
        if district:
            params["district"] = district
        return await _read(ctx, "/data/municipalities/statistics", params)

    @server.tool()
    async def nearby_places(
        origin_id: str,
        category: str | None = None,
        radius_m: int = 5000,
        limit: int = 10,
        ctx: Context = None,
    ) -> dict:
        """Find loaded POI within measured geodesic radius, ranked by actual straight-line
        distance, NOT driving distance. category: healthcare, education, transport, shopping.
        Use a resolved origin ID; radius <=50000 m. Empty results do not prove no real facilities.
        """
        params = {"origin_id": origin_id, "radius_m": radius_m, "limit": limit}
        if category:
            params["category"] = category
        return await _read(ctx, "/data/places/nearby", params)

    @server.tool()
    async def measure_distance(from_id: str, to_id: str, ctx: Context) -> dict:
        """Compute exact WGS84 geodesic distance between representative points of resolved
        places. For driving distance call find_route instead. Never guess coordinates.
        """
        return await _read(ctx, "/data/distance", {"from_id": from_id, "to_id": to_id})

    @server.tool()
    async def find_route(from_id: str, to_id: str, ctx: Context) -> dict:
        """Compute a real driving route via OSRM/OSM with geometry, road distance and modelled
        duration (no live traffic). Only driving is supported. Failure must not become an estimate.
        Municipalities use representative interior points; request precise places if needed.
        """
        return await _read(ctx, "/data/route", {"from_id": from_id, "to_id": to_id})

    @server.tool()
    async def show_map(result_id: str) -> dict:
        """Display and fit verified result geometry on the user's map. Reference a result_id
        supplied by the chat host; do not supply or invent geometry. Chat host validates the reference.
        """
        return {"presentation": {"result_id": result_id, "view": "map"}}

    @server.tool()
    async def show_table(result_id: str) -> dict:
        """Display verified result rows as an interactive sortable table with CSV export.
        Reference a result_id from the chat host; never retype values.
        """
        return {"presentation": {"result_id": result_id, "view": "table"}}

    @server.tool()
    async def show_chart(result_id: str, value_key: str, label_key: str, kind: str = "bar") -> dict:
        """Display a bar or line chart of a verified result. Use actual numeric value_key and
        label_key from its columns. A line chart preserves returned row order; don't imply a time trend for unordered categories.
        """
        return {
            "presentation": {
                "result_id": result_id,
                "view": kind,
                "value_key": value_key,
                "label_key": label_key,
            }
        }

    @server.tool()
    async def filter_result(
        result_id: str, sort_key: str, descending: bool = True, limit: int = 10
    ) -> dict:
        """Sort and select up to 50 rows from a known result without retyping data. Host verifies
        column names and computes the selection. The result only covers the original returned subset.
        """
        return {
            "transform": {
                "result_id": result_id,
                "sort_key": sort_key,
                "descending": descending,
                "limit": limit,
            }
        }

    @server.tool()
    async def load_map_layer(
        layer: str, around_id: str, radius_m: int = 2000, limit: int = 100, ctx: Context = None
    ) -> dict:
        """Load actual vector features around a resolved place, ready for show_map.
        layer: flood, protected, roads, water, parcels. radius <=10000 m; max 200 features.
        Respect truncation: these are local data within a bounded area, not an exhaustive national layer.
        """
        return await _read(
            ctx,
            "/data/layers",
            {"layer": layer, "around_id": around_id, "radius_m": radius_m, "limit": limit},
        )

    @server.tool()
    async def parcel_at_point(lat: float, lon: float, ctx: Context) -> dict:
        """Resolve parcels at a user's map click or previously verified coordinates. Never
        guess coordinates. Returns actual boundaries and cadastral attributes, possibly multiple hits at a boundary.
        """
        return await _read(ctx, "/data/parcels/at-point", {"lat": lat, "lon": lon})

    @server.tool()
    async def set_map_layer(result_id: str, visible: bool) -> dict:
        """Show or hide one verified result layer in the map. Refer to a current or restored
        result_id. Does not delete data or affect other layers. Chat host validates the reference.
        """
        return {"layer_action": {"result_id": result_id, "visible": visible}}

    @server.tool()
    async def compare_results(result_ids: list[str]) -> dict:
        """Combine 2–6 verified result references with identical fields/units for side-by-side
        comparison, e.g. parcels selected by clicking. No hand-entered values; host validates schemas.
        """
        return {"transform": {"kind": "combine", "result_ids": result_ids}}

    @server.tool()
    async def summarize_result(result_id: str, value_key: str, operation: str) -> dict:
        """Compute min/max/mean/sum/count of a numeric column in an existing verified result.
        The host computes values; do not infer a whole-dataset total from a limited selection.
        """
        return {
            "transform": {
                "kind": "aggregate",
                "result_id": result_id,
                "value_key": value_key,
                "operation": operation,
            }
        }
