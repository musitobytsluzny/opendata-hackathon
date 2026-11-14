"""Authenticated read-only tools. Each request forwards its own user token."""

import httpx
from mcp.server.fastmcp import Context, FastMCP
from services.api_client import get_api_client


async def _read(ctx: Context, path: str, params=None, timeout=None) -> dict:
    request = ctx.request_context.request
    authorization = request.headers.get("authorization", "") if request else ""
    if not authorization.lower().startswith("bearer "):
        return {"error": "Přihlášení je vyžadované.", "status": 401}
    try:
        response = await get_api_client().client.get(
            path,
            params=params,
            headers={"Authorization": authorization},
            **({"timeout": timeout} if timeout is not None else {}),
        )
        if response.is_error:
            message = "Datový dotaz se nepodařil."
            if 400 <= response.status_code < 500:
                try:
                    detail = response.json().get("detail")
                except (ValueError, AttributeError):
                    detail = None
                if isinstance(detail, str):
                    message = detail[:1000]
            return {"error": message, "status": response.status_code}
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
        """Read indicative spatial checks, zoning plan (územní plán / funkční využití / zastavitelnost)
        and radon risk at known WGS84 coordinates; never guess coordinates.
        """
        return await _read(ctx, "/data/prevalidate/point", {"lat": lat, "lon": lon})

    @server.tool()
    async def prevalidate_parcel(
        cislo: str,
        kod_ku: int | None = None,
        nazev_ku: str | None = None,
        ctx: Context = None,
    ) -> dict:
        """Read indicative parcel checks, zoning plan (územní plán / funkční využití / zastavitelnost)
        and radon risk using parcel number (cislo, e.g. '841/1' or '969') and either cadastral-area code
        (kod_ku, e.g. 722618) or cadastral-area name (nazev_ku, e.g. 'Bolevec', 'Plzeň').
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
        """Find parcel and read indicative spatial checks, zoning plan (územní plán / funkční využití /
        zastavitelnost) and radon risk based on address or house number (číslo popisné / orientační),
        street, and municipality (e.g. 'Koterovská 85, Plzeň' or cislo_popisne=1, obec='Plzeň').
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
        healthcare, transport, or amenities by name, category, or municipality. Supported
        categories are healthcare, education, transport, and shopping; unsupported categories
        such as sports or cultural facilities return no matches with a coverage note.
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
        Also supports area_m2 computed from real municipality polygons. Returns verified rows suitable for tables, charts and map points.
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
    async def show_chart(
        result_id: str, value_key: str, label_key: str, kind: str = "auto"
    ) -> dict:
        """Display an auto-selected, bar, line or pie chart of a verified result. Use actual numeric value_key and
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
        comparison. For parcels: first prevalidate_parcel for EACH clicked parcel using name and kod_ku, then combine the NEW assessment result_ids. Click results alone do not assess restrictions. Use the returned combined result_id for the comparative chart, never an original one-row ID. No hand-entered values; host validates schemas.
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

    @server.tool()
    async def nearest_municipalities(
        origin_id: str,
        limit: int = 3,
        radius_m: int = 50000,
        cities_only: bool = False,
        ctx: Context = None,
    ) -> dict:
        """Find actual nearest neighbours without the user naming candidates. Resolve origin
        with search_places, then rank loaded municipalities by measured WGS84 distance between
        interior points. cities_only=true restricts to official RÚIAN cities (not villages).
        Excludes the origin municipality. radius <=200000 m, limit <=20. For driving ranking,
        pass discovered IDs to rank_driving_candidates; do not label straight-line distances as road distances.
        """
        return await _read(
            ctx,
            "/data/municipalities/nearest",
            {
                "origin_id": origin_id,
                "limit": limit,
                "radius_m": radius_m,
                "cities_only": cities_only,
            },
        )

    @server.tool()
    async def alternative_municipalities(
        origin_id: str,
        population_difference_pct: float = 50,
        radius_m: int = 50000,
        cities_only: bool = False,
        limit: int = 5,
        ctx: Context = None,
    ) -> dict:
        """Find nearby alternative municipalities with similar measured population, within
        ±population_difference_pct (0–100) of the origin. Explicit similarity criterion, not a
        subjective quality-of-life score. Exact census values and actual distance; no invented prices or safety ratings.
        """
        return await _read(
            ctx,
            "/data/municipalities/nearest",
            {
                "origin_id": origin_id,
                "limit": limit,
                "radius_m": radius_m,
                "cities_only": cities_only,
                "population_difference_pct": population_difference_pct,
            },
        )

    @server.tool()
    async def nearby_facilities(
        origin_id: str, kind: str, radius_m: int = 10000, limit: int = 5, ctx: Context = None
    ) -> dict:
        """Find nearest actual everyday facilities. kind: school, primary_school, secondary_school, university, kindergarten, hospital,
        healthcare, pharmacy, public_transport, railway_station, grocery. Hospital means hospital,
        not any doctor. Uses loaded OSM/ČÚZK/PMDP data and returns publishers and map geometry.
        Distances are geodesic, not walking/driving time. Expand radius if empty; do not claim the service doesn't exist.
        """
        return await _read(
            ctx,
            "/data/facilities/nearby",
            {"origin_id": origin_id, "kind": kind, "radius_m": radius_m, "limit": limit},
        )

    @server.tool()
    async def accessibility_summary(
        origin_id: str, radius_m: int = 20000, ctx: Context = None
    ) -> dict:
        """Neighbourhood everyday-life overview: nearest loaded school, kindergarten, hospital,
        pharmacy, public transport and grocery, with actual distances and missing values explicit.
        Suitable for evaluating a selected parcel or comparing places. No implied opening hours,
        school capacity, departures, transit frequency or arbitrary liveability scores.
        """
        return await _read(
            ctx, "/data/accessibility", {"origin_id": origin_id, "radius_m": radius_m}
        )

    @server.tool()
    async def facility_alternatives(
        place_id: str,
        radius_m: int = 20000,
        limit: int = 5,
        kind: str | None = None,
        ctx: Context = None,
    ) -> dict:
        """Find other facilities near a known facility, excluding itself and duplicate campuses.
        Schools default to all school levels, NOT implicitly the origin's level. Pass kind
        (e.g. primary_school or secondary_school) only when that level is explicitly requested.
        Hospitals stay hospitals; stops stay public transport. Does not assert capacity or current availability.
        """
        return await _read(
            ctx,
            "/data/facilities/alternatives",
            {
                "place_id": place_id,
                "radius_m": radius_m,
                "limit": limit,
                **({"kind": kind} if kind else {}),
            },
        )

    @server.tool()
    async def rank_driving_candidates(
        origin_id: str, candidate_ids: list[str], ctx: Context, order_by: str = "distance"
    ) -> dict:
        """Compare 1–8 verified candidate IDs by real OSRM driving distance and modelled duration
        in one routing matrix query. order_by=duration means fastest by minutes; order_by=distance means shortest by km (default). Never conflate them. Discover candidates first using nearest_municipalities or
        nearby_facilities. Ranking applies only to these candidates, not all possible places.
        Missing routes remain missing; never substitute guessed times or straight-line estimates.
        """
        return await _read(
            ctx,
            "/data/routes/rank",
            {"origin_id": origin_id, "candidate_ids": candidate_ids, "order_by": order_by},
        )

    @server.tool()
    async def comparison_summary(result_ids: list[str]) -> dict:
        """Prepare a grounded family/decision summary of 2–6 compared parcels from verified
        result references. Include parcel results and driving results where available (max 8 refs).
        The host computes area differences, preserves route origins and renders facts and unknowns.
        No guessed garden space, building permission, school capacity or liveability claims.
        Use for 'shrň poslední porovnání pro rodinu'; do not substitute speculative prose.
        """
        return {"comparison_summary": {"result_ids": result_ids}}

    @server.tool()
    async def route_context(
        origin_id: str, destination_id: str, corridor_m: int = 30, ctx: Context = None
    ) -> dict:
        """Inspect actual map features along a computed FOOT route to school (FOSSGIS OSRM foot).
        Uses a 10–100 m corridor and real intersections/proximity queries for flood zones,
        watercourses, mapped crossings/signals, road classes and explicit/missing OSM sidewalk tags.
        Mandatory before any statement about hazards or absence of features ALONG a journey;
        endpoint checks or driving routes cannot substitute. This is NOT a child-safety rating.
        Missing tags are unknown, watercourses aren't automatically hazards, bridges/traffic/weather
        and real-world conditions aren't verified. Return exact mapped findings and unknowns, never 'safe'.
        """
        return await _read(
            ctx,
            "/data/routes/context",
            {"origin_id": origin_id, "destination_id": destination_id, "corridor_m": corridor_m},
        )

    @server.tool()
    async def balanced_parcels(
        first_id: str, second_id: str, tolerance_m: float = 25, limit: int = 5, ctx: Context = None
    ) -> dict:
        """Search ALL loaded parcels for the smallest difference of WGS84 geodesic distances
        to two verified institution IDs (facility:/poi: from search_amenities). Searches the whole
        loaded region, not a radius or arbitrary shortlist. Returns actual polygons automatically.
        Tolerance is explicit (default 25 m), tested BEFORE rounding; false means outside tolerance.
        Exact numeric equality uses tolerance_m=0, never implies accuracy of the source in terrain.
        For an explicitly local radius use balanced_parcels_nearby instead. This tool cannot silently
        narrow the scope. Do not substitute a nearby address parcel for a verified institution.
        No building/prosale/entrance/driving guarantees. Driving follow-up requires routes FROM
        each candidate parcel TO both institutions, not a claim of a global driving optimum.
        """
        return await _read(
            ctx,
            "/data/parcels/balanced",
            {
                "first_id": first_id,
                "second_id": second_id,
                "search_all": True,
                "tolerance_m": tolerance_m,
                "limit": limit,
            },
            timeout=35,
        )

    @server.tool()
    async def balanced_parcels_nearby(
        first_id: str,
        second_id: str,
        radius_m: int = 5000,
        tolerance_m: float = 25,
        limit: int = 5,
        ctx: Context = None,
    ) -> dict:
        """LOCAL variant only when the user requests a radius near the midpoint of two places.
        Measures geodesic distances from parcel interior points, searches all loaded candidates in
        radius 100–20000 m (default 5 km), never the whole region. Reports scope, tolerance and polygons.
        For whole database or unspecified scope use balanced_parcels instead. No driving/building guarantees.
        """
        return await _read(
            ctx,
            "/data/parcels/balanced",
            {
                "first_id": first_id,
                "second_id": second_id,
                "search_all": False,
                "radius_m": radius_m,
                "tolerance_m": tolerance_m,
                "limit": limit,
            },
            timeout=35,
        )
