"""Export reproducible parcel and regional previews, never chat history or private homes."""

import json
from datetime import datetime, timezone

from app.services import geo_data, life_data, workspace_data
from sqlalchemy import text


def place(name):
    rows = workspace_data.search_places(name)["result"]["rows"]
    exact = [row for row in rows if row["name"] == name]
    if len(exact) != 1:
        raise ValueError(f"Expected one public municipality: {name}")
    return exact[0]["id"]


def main():
    parcel_check = geo_data.prevalidate_parcel("438/1", kod_ku=722120)
    parcel = parcel_check.get("parcel")
    if not parcel:
        raise ValueError(f"Expected a verified parcel in Bolevec: {parcel_check}")
    parcel_title = f"Parcela {parcel['cislo_parcely']} · {parcel['ku_nazev']}"
    parcel_result = workspace_data.place_geometry(f"parcela:{parcel['id']}")["result"]
    if len(parcel_result["features"]) != 1:
        raise ValueError(f"Expected one parcel geometry: {parcel_title}")
    parcel_result["features"][0]["properties"]["label"] = parcel_title
    parcel_result["rows"] = [
        {
            "id": f"parcela:{parcel['id']}",
            "name": parcel_title,
            "area_m2": parcel.get("vymera_m2"),
            "land_type": parcel.get("druh_pozemku"),
        }
    ]
    parcel_result["columns"] = [
        {"key": "name", "label": "Parcela"},
        {"key": "area_m2", "label": "Výměra", "numeric": True, "unit": "m²"},
        {"key": "land_type", "label": "Druh pozemku"},
    ]
    parcel_result["note"] = (
        "Výměra a druh pozemku jsou údaje evidované v RÚIAN. "
        "Samy o sobě nepotvrzují vlastnictví ani možnost stavby."
    )

    plzen, klatovy, rokycany, domazlice = [
        place(n) for n in ["Plzeň", "Klatovy", "Rokycany", "Domažlice"]
    ]
    driving = life_data.rank_driving_candidates(plzen, [klatovy, rokycany, domazlice])["result"]
    driving["features"] = []
    for target in [klatovy, rokycany, domazlice]:
        driving["features"].extend(workspace_data.find_route(plzen, target)["result"]["features"])
    # Remove duplicated origin points without removing distinct route lines.
    for index, f in enumerate(driving["features"]):
        if f["geometry"]["type"] == "LineString":
            f["id"] = f"public-route-{index}"
    driving["features"] = list({str(f["id"]): f for f in driving["features"]}.values())
    population = workspace_data.municipality_statistics("population", limit=5)["result"]
    for f, row in zip(population["features"], population["rows"], strict=True):
        f["properties"]["label"] = f"{row['name']} · {int(row['value']):,} obyvatel".replace(
            ",", " "
        )
    alternatives = life_data.nearest_municipalities(
        rokycany, limit=5, radius_m=100000, population_difference_pct=30
    )["result"]
    floods = workspace_data.load_map_layer("flood", plzen, radius_m=5000, limit=100)["result"]
    # Clip long river-basin polygons to the preview area, then generalize in metres.
    # Keep real geometry while avoiding a multi-megabyte landing payload.
    with workspace_data.read_connection() as connection:
        center = workspace_data.resolve(connection, plzen)["point"]
        visible = []
        for feature in floods["features"]:
            geometry = connection.scalar(
                text(
                    "SELECT ST_AsGeoJSON(ST_Transform(ST_SimplifyPreserveTopology(ST_Transform(ST_Intersection(ST_SetSRID(ST_GeomFromGeoJSON(:geom),4326),ST_Buffer(ST_SetSRID(ST_GeomFromGeoJSON(:center),4326)::geography,5000)::geometry),5514),25),4326))"
                ),
                {"geom": json.dumps(feature["geometry"]), "center": center},
            )
            parsed = json.loads(geometry)
            if parsed.get("coordinates"):
                visible.append(dict(feature, geometry=parsed))
        floods["features"] = visible
        floods["note"] += (
            " Náhledové geometrie jsou oříznuté na okruh 5 km a zjednodušené s tolerancí 25 m."
        )
    distance_text = "; ".join(
        f"{row['name']}: {row['distance_km']} km, {row['duration_min']} min"
        for row in driving["rows"]
    )
    population_text = ", ".join(
        f"{r['name']} ({int(r['value']):,})".replace(",", " ") for r in population["rows"]
    )
    alternative_text = ", ".join(
        f"{r['name']} ({r['population']:,} obyvatel)".replace(",", " ")
        for r in alternatives["rows"]
    )
    examples = [
        (
            parcel_title,
            "Reality a katastr",
            f"Jak je v katastru evidována parcela {parcel['cislo_parcely']} v katastrálním území {parcel['ku_nazev']} a jakou má výměru?",
            f"Parcela má výměru {parcel.get('vymera_m2')} m² a je evidována jako {parcel.get('druh_pozemku') or 'pozemek bez uvedeného druhu'}. "
            "Údaj o druhu pozemku a výměře vychází z RÚIAN; nepotvrzuje vlastnictví ani možnost stavby.",
            parcel_result,
        ),
        (
            "Kam vyrazit z Plzně",
            "Doprava",
            "Co je z Plzně blíž autem: Rokycany, Klatovy, nebo Domažlice? Porovnej dojezdy a ukaž trasy na mapě.",
            f"{distance_text}. Modelové časy bez živé dopravy mezi referenčními body obcí.",
            driving,
        ),
        (
            "Kde žije nejvíc lidí",
            "Obce a obyvatelstvo",
            "Kterých pět obcí Plzeňského kraje má nejvíc obyvatel? Porovnej je v grafu a ukaž na mapě.",
            f"{population_text}. Počet obyvatel z načtených dat ČSÚ; pět nejlidnatějších obcí kraje.",
            population,
        ),
        (
            "Alternativy v kraji",
            "Obce a obyvatelstvo",
            "Najdi do 100 km od Rokycan obce s podobným počtem obyvatel, v rozmezí ±30 %. Porovnej je na mapě.",
            f"{alternative_text}. Podobnost podle počtu obyvatel, vzdálenost vzdušně mezi referenčními body obcí.",
            alternatives,
        ),
        (
            "Řeky a záplavové zóny",
            "Příroda a rizika",
            "Ukaž záplavová území v okruhu 5 km od referenčního bodu Plzně. Kde se nacházejí a co z těchto dat nelze zjistit?",
            f"Na mapě je {len(floods['features'])} prvků záplavových vrstev. Jde o evidovaná území, nikoli aktuální rozliv nebo předpověď povodně. "
            + floods["note"],
            floods,
        ),
    ]
    print(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "examples": [
                    {
                        "title": title,
                        "category": category,
                        "question": question,
                        "answer": answer,
                        "features": data["features"],
                        "rows": data["rows"],
                        "sources": data["sources"],
                        "note": data["note"],
                        "source_label": "OSRM · ČÚZK"
                        if category == "Doprava"
                        else (
                            "ČSÚ · ČÚZK"
                            if category == "Obce a obyvatelstvo"
                            else (
                                "ČÚZK · RÚIAN" if category == "Reality a katastr" else "VÚV · ČÚZK"
                            )
                        ),
                    }
                    for title, category, question, answer, data in examples
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
