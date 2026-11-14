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
