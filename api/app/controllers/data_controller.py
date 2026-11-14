from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.schemas.chat import Metric
from app.services import geo_data

router = APIRouter(prefix="/data", tags=["Data"], dependencies=[Depends(get_current_user)])


@router.get("/catalog")
def dataset_catalog():
    return geo_data.catalog()


@router.get("/statistics")
def district_statistics(metric: Metric):
    if metric == "area_m2":
        raise HTTPException(422, "Pro rozlohu jednotlivých obcí použijte municipality_statistics.")
    return geo_data.statistics(metric)


@router.get("/prevalidate/point")
def point(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    return geo_data.prevalidate_point(lat, lon)


@router.get("/prevalidate/parcel")
def parcel(
    cislo: str = Query(max_length=50, pattern=r"^[0-9]+(?:/[0-9]+)?$"),
    kod_ku: int | None = Query(default=None, gt=0),
    nazev_ku: str | None = Query(default=None, max_length=100),
):
    if kod_ku is None and not nazev_ku:
        raise HTTPException(400, "Je nutné zadat kod_ku nebo nazev_ku.")
    return geo_data.prevalidate_parcel(cislo=cislo, kod_ku=kod_ku, nazev_ku=nazev_ku)


@router.get("/prevalidate/address")
def address(
    adresa: str | None = Query(default=None, max_length=200),
    cislo_popisne: int | None = Query(default=None, gt=0),
    cislo_orientacni: int | None = Query(default=None, gt=0),
    obec: str | None = Query(default=None, max_length=100),
    ulice: str | None = Query(default=None, max_length=100),
):
    if not any([adresa, cislo_popisne, obec, ulice]):
        raise HTTPException(400, "Je nutné zadat adresu nebo alespoň číslo popisné / obec / ulici.")
    return geo_data.prevalidate_address(
        adresa=adresa,
        cislo_popisne=cislo_popisne,
        cislo_orientacni=cislo_orientacni,
        obec=obec,
        ulice=ulice,
    )


@router.get("/amenities")
def amenities(
    query: str = Query(min_length=2, max_length=100),
    obec: str | None = Query(default=None, max_length=100),
    kategorie: str | None = Query(default=None, max_length=50),
):
    return geo_data.search_amenities(query=query, obec=obec, kategorie=kategorie)


from app.services import chat_results, workspace_data  # noqa: E402


@router.get("/places/search")
def search_places(
    query: str = Query(min_length=2, max_length=100),
    kind: str = Query(default="obec", pattern="^(obec|ku|poi|parcela)$"),
    limit: int = Query(default=10, ge=1, le=30),
):
    return workspace_data.search_places(query, kind, limit)


@router.get("/places/geometry")
def place_geometry(place_id: str = Query(min_length=3, max_length=80)):
    return workspace_data.place_geometry(place_id)


@router.get("/municipalities/statistics")
def municipality_statistics(
    metric: Metric,
    district: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    descending: bool = True,
):
    return workspace_data.municipality_statistics(metric, district, limit, descending)


@router.get("/places/nearby")
def nearby_places(
    origin_id: str = Query(max_length=80),
    category: str | None = Query(default=None, max_length=30),
    radius_m: int = Query(default=5000, ge=1, le=50000),
    limit: int = Query(default=10, ge=1, le=30),
):
    return workspace_data.nearby_places(origin_id, category, radius_m, limit)


@router.get("/distance")
def measure_distance(from_id: str = Query(max_length=80), to_id: str = Query(max_length=80)):
    return workspace_data.measure_distance(from_id, to_id)


@router.get("/route")
def find_route(from_id: str = Query(max_length=80), to_id: str = Query(max_length=80)):
    return workspace_data.find_route(from_id, to_id)


@router.get("/layers")
def map_layer(
    layer: str = Query(pattern="^(flood|protected|roads|water|parcels)$"),
    around_id: str = Query(max_length=80),
    radius_m: int = Query(default=2000, ge=50, le=10000),
    limit: int = Query(default=100, ge=1, le=200),
):
    return workspace_data.load_map_layer(layer, around_id, radius_m, limit)


@router.get("/parcels/at-point")
def parcel_at_point(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    user=Depends(get_current_user),
):
    payload = workspace_data.parcel_at_point(lat, lon)
    artifact = chat_results.remember(payload["result"], user.id)
    return {"result": artifact.model_dump()}


from app.services import life_data  # noqa: E402


@router.get("/municipalities/nearest")
def nearest_municipalities(
    origin_id: str = Query(max_length=80),
    limit: int = Query(default=3, ge=1, le=20),
    radius_m: int = Query(default=50000, ge=100, le=200000),
    cities_only: bool = False,
    population_difference_pct: float | None = Query(default=None, ge=0, le=100),
):
    return life_data.nearest_municipalities(
        origin_id, limit, radius_m, cities_only, population_difference_pct
    )


@router.get("/facilities/nearby")
def nearby_facilities(
    origin_id: str = Query(max_length=80),
    kind: str = Query(max_length=30),
    radius_m: int = Query(default=10000, ge=50, le=100000),
    limit: int = Query(default=5, ge=1, le=20),
):
    return life_data.nearby_facilities(origin_id, kind, radius_m, limit)


@router.get("/accessibility")
def accessibility_summary(
    origin_id: str = Query(max_length=80), radius_m: int = Query(default=20000, ge=100, le=100000)
):
    return life_data.accessibility_summary(origin_id, radius_m)


@router.get("/facilities/alternatives")
def facility_alternatives(
    place_id: str = Query(max_length=80),
    radius_m: int = Query(default=20000, ge=50, le=100000),
    limit: int = Query(default=5, ge=1, le=20),
):
    return life_data.facility_alternatives(place_id, radius_m, limit)


@router.get("/routes/rank")
def rank_driving_candidates(
    origin_id: str = Query(max_length=80),
    candidate_ids: list[str] = Query(min_length=1, max_length=8),
):
    return life_data.rank_driving_candidates(origin_id, candidate_ids)
