from fastapi import APIRouter, Depends, Query

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
    kod_ku: int = Query(gt=0), cislo: str = Query(max_length=50, pattern=r"^[0-9]+(?:/[0-9]+)?$")
):
    return geo_data.prevalidate_parcel(kod_ku, cislo)
