"""Bounded, user-scoped short-lived references to verified tool results."""

import json
import re
import threading
import time
from collections import OrderedDict
from secrets import token_hex
from urllib.parse import parse_qs

from app.schemas.chat import ChatArtifact

_cache: OrderedDict[str, tuple[int, float, ChatArtifact]] = OrderedDict()
TTL = 900
PER_USER_LIMIT = 32
_cache_lock = threading.RLock()


def remember(payload, user_id):
    if len(json.dumps(payload, ensure_ascii=False)) > 450000:
        raise ValueError("Výsledek je příliš velký; zmenši oblast nebo počet prvků.")
    artifact = ChatArtifact.model_validate(dict(payload, result_id=token_hex(12)))
    with _cache_lock:
        now = time.monotonic()
        for key, (_, created, _) in list(_cache.items()):
            if now - created > TTL:
                _cache.pop(key, None)
        own = [key for key, (owner, _, _) in _cache.items() if owner == user_id]
        for key in own[: max(0, len(own) - PER_USER_LIMIT + 1)]:
            _cache.pop(key, None)
        _cache[artifact.result_id] = (user_id, now, artifact)
        while len(_cache) > 128:
            _cache.popitem(last=False)
    return artifact


def restore(ids, user_id):
    results = {}
    with _cache_lock:
        for key in ids:
            entry = _cache.get(key)
            if entry is not None:
                owner, created, artifact = entry
                if time.monotonic() - created > TTL:
                    _cache.pop(key, None)
                elif owner == user_id:
                    results[key] = artifact
    return results


def model_context(artifact):
    data = artifact.model_dump(exclude={"features"})
    data["feature_count"] = len(artifact.features)
    return data


def present(intent, results):
    artifact = results.get(intent.get("result_id"))
    if artifact is None:
        raise ValueError("Výsledek neexistuje nebo vypršel; nejprve znovu načti data.")
    view = intent.get("view")
    if view == "auto":
        label_key = intent.get("label_key")
        labels = [str(row.get(label_key, "")) for row in artifact.rows]
        temporal = (
            label_key in {"year", "date", "rok", "datum"}
            and len(set(labels)) > 1
            and labels == sorted(labels)
        )
        view = "line" if temporal else "bar"
    if view not in {"table", "map", "bar", "line", "pie"}:
        raise ValueError("Neznámý typ zobrazení.")
    if view == "map" and not artifact.features:
        raise ValueError("Výsledek nemá geometrii pro mapu.")
    if view in {"bar", "line", "pie"}:
        columns = {column.key: column for column in artifact.columns}
        value = columns.get(intent.get("value_key"))
        if value is None or not value.numeric or intent.get("label_key") not in columns:
            raise ValueError("Graf vyžaduje existující číselný sloupec a sloupec popisků.")
    if view == "pie":
        values = [row.get(value.key) for row in artifact.rows]
        if (
            not value.additive
            or not 2 <= len(values) <= 12
            or any(not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0 for v in values)
            or sum(values) <= 0
        ):
            raise ValueError(
                "Koláč vyžaduje 2–12 nezáporných sčitatelných hodnot s kladným součtem. Pro procenta, indexy nebo chybějící hodnoty použij sloupce."
            )
    return ChatArtifact.model_validate(
        dict(
            artifact.model_dump(),
            view=view,
            value_key=intent.get("value_key"),
            label_key=intent.get("label_key"),
        )
    )


def transform(intent, results, user_id):
    artifact = results.get(intent.get("result_id"))
    if artifact is None:
        raise ValueError("Výsledek neexistuje nebo vypršel.")
    key = intent.get("sort_key")
    if key not in {column.key for column in artifact.columns}:
        raise ValueError("Sloupec pro řazení neexistuje.")
    limit = intent.get("limit", 10)
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("Počet řádků musí být 1 až 50.")
    values = [row for row in artifact.rows if row.get(key) is not None]

    def sort_value(row):
        value = row[key]
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        return (numeric, value if numeric else str(value))

    rows = sorted(values, key=sort_value, reverse=bool(intent.get("descending", True)))[:limit]
    ids = {row.get("id") for row in rows}
    features = [feature for feature in artifact.features if feature.get("id") in ids]
    data = dict(
        artifact.model_dump(exclude={"result_id"}),
        rows=rows,
        features=features,
        note=artifact.note + " Výběr z předchozího výsledku, nikoli z celé databáze.",
    )
    return remember(data, user_id)


def combine(intent, results, user_id):
    ids = intent.get("result_ids", [])
    if not 2 <= len(ids) <= 6 or len(set(ids)) != len(ids):
        raise ValueError("Porovnej 2 až 6 různých ověřených výsledků.")
    items = [results.get(key) for key in ids]
    if any(item is None for item in items):
        raise ValueError("Některý výsledek vypršel nebo není dostupný.")
    schema = [(column.key, column.numeric, column.unit) for column in items[0].columns]
    if any(
        [(column.key, column.numeric, column.unit) for column in item.columns] != schema
        for item in items
    ):
        raise ValueError("Výsledky nemají stejná pole a jednotky; nelze je přímo porovnat.")
    rows = [row for item in items for row in item.rows]
    if any(
        str(row.get("id", "")).startswith("parcela:") and row.get("assessment_kind") != "indicative"
        for row in rows
    ):
        raise ValueError(
            "Pro porovnání parcel nejprve zavolej prevalidate_parcel pro každou parcelu podle name/cislo_parcely a kod_ku z kliknutí. Poté spoj NOVÉ výsledky těchto kontrol; samotné kliknutí neověřuje omezení."
        )
    if len(rows) > 50:
        raise ValueError("Porovnání smí mít nejvýše 50 řádků; nejprve omez výběr.")
    features = {str(feature.get("id")): feature for item in items for feature in item.features}
    sources = list(
        {
            json.dumps(source, sort_keys=True): source for item in items for source in item.sources
        }.values()
    )
    return remember(
        {
            "title": "Porovnání výsledků",
            "columns": [column.model_dump() for column in items[0].columns],
            "rows": rows,
            "features": list(features.values()),
            "sources": sources,
            "sample": any(item.sample for item in items),
            "note": "Porovnání ověřených výběrů. "
            + " ".join(dict.fromkeys(item.note for item in items)),
        },
        user_id,
    )


def aggregate(intent, results, user_id):
    import statistics

    artifact = results.get(intent.get("result_id"))
    if artifact is None:
        raise ValueError("Výsledek není dostupný.")
    key = intent.get("value_key")
    column = next(
        (column for column in artifact.columns if column.key == key and column.numeric), None
    )
    operation = intent.get("operation")
    if column is None or operation not in {"min", "max", "mean", "sum", "count"}:
        raise ValueError("Vyber existující číselný sloupec a operaci min/max/mean/sum/count.")
    values = [
        row[key]
        for row in artifact.rows
        if isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)
    ]
    if not values:
        raise ValueError("Sloupec nemá dostupné číselné hodnoty.")
    functions = {"min": min, "max": max, "mean": statistics.mean, "sum": sum, "count": len}
    return remember(
        {
            "title": f"{operation}: {column.label}",
            "columns": [
                {"key": "operation", "label": "Operace"},
                {
                    "key": "value",
                    "label": column.label,
                    "numeric": True,
                    "unit": "" if operation == "count" else column.unit,
                },
            ],
            "rows": [{"operation": operation, "value": functions[operation](values)}],
            "sources": artifact.sources,
            "sample": artifact.sample,
            "note": f"Výpočet z {len(values)} neprázdných hodnot vráceného výběru, nikoliv z celé databáze. "
            + artifact.note,
        },
        user_id,
    )


def comparison_summary(intent, results, user_id):
    """A factual decision brief; no generated claims about buildability or free space."""
    ids = intent.get("result_ids", [])
    if not 1 <= len(ids) <= 8 or any(key not in results for key in ids):
        raise ValueError(
            "Vyber 1–8 dostupných ověřených výsledků obsahujících porovnávané parcely a případné trasy."
        )
    items = [results[key] for key in ids]
    parcels, routes = {}, []
    for item in items:
        for row in item.rows:
            if str(row.get("id", "")).startswith("parcela:") and row.get("area_m2") is not None:
                previous = parcels.setdefault(row["id"], {})
                previous.update({key: value for key, value in row.items() if value is not None})
            if row.get("from_id") and row.get("distance_km") is not None:
                routes.append(row)
    if not 2 <= len(parcels) <= 6:
        raise ValueError(
            "Pro shrnutí jsou potřeba skutečné výměry 2–6 různých parcel. Nejprve načti jejich údaje."
        )

    # Enrich only the selected parcels from other verified context results. This
    # preserves assessments and route origins even when a caller names a basic click result.
    related = [
        item
        for item in results.values()
        if item not in items
        and any(row.get("id") in parcels or row.get("from_id") in parcels for row in item.rows)
    ]
    items.extend(related)
    for item in related:
        for row in item.rows:
            if row.get("id") in parcels and row.get("area_m2") is not None:
                parcels[row["id"]].update(
                    {
                        key: value
                        for key, value in row.items()
                        if value is not None
                        or key in {"flood_q20", "flood_q100", "active_flood_zone", "protected_area"}
                    }
                )
            if row.get("from_id") in parcels and row.get("distance_km") is not None:
                routes.append(row)
    if any(row.get("assessment_kind") != "indicative" for row in parcels.values()):
        raise ValueError(
            "Nejprve prověř každou vybranou parcelu pomocí prevalidate_parcel (číslo a kod_ku jsou v řádcích kliknutí). Samotná výměra z mapy není kontrolou omezení."
        )

    def cell(value):
        return (
            str(value if value is not None else "nezjištěno").replace("|", "/").replace("\n", " ")
        )

    def number(value):
        return f"{float(value):,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")

    labels = {
        key: cell(row.get("cislo_parcely") or row.get("name") or key)
        for key, row in parcels.items()
    }
    lines = [
        "### Naměřená fakta",
        "",
        "| Parcela | Celková výměra | Katastrální druh pozemku |",
        "| --- | ---: | --- |",
    ]
    for key, row in parcels.items():
        lines.append(
            f"| {labels[key]} | {number(row['area_m2'])} m² | {cell(row.get('land_type'))} |"
        )
    if any(
        any(
            key in row for key in ("flood_q20", "flood_q100", "active_flood_zone", "protected_area")
        )
        for row in parcels.values()
    ):

        def finding(value):
            return (
                "zjištěn"
                if value is True
                else "nezjištěn v datech"
                if value is False
                else "neověřeno"
            )

        lines.extend(
            [
                "",
                "### Průniky s dostupnými vrstvami",
                "",
                "| Parcela | Q20 | Q100 | Aktivní záplavová zóna | Ochrana přírody |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for key, row in parcels.items():
            lines.append(
                "| "
                + labels[key]
                + " | "
                + " | ".join(
                    finding(row.get(field))
                    for field in ("flood_q20", "flood_q100", "active_flood_zone", "protected_area")
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "Nezjištěný průnik je pouze výsledek kontroly načtených vrstev; není zárukou absence rizik ani jiných omezení.",
            ]
        )
    routes = [row for row in routes if row["from_id"] in parcels]
    if routes:
        lines.extend(
            [
                "",
                "### Dostupnost autem",
                "",
                "| Z parcely | Cíl | Délka trasy | Modelový čas |",
                "| --- | --- | ---: | ---: |",
            ]
        )
        unique = set()
        for row in routes:
            route_key = (row["from_id"], row.get("id") or row.get("to_id"), row["distance_km"])
            if route_key in unique:
                continue
            unique.add(route_key)
            lines.append(
                f"| {labels[row['from_id']]} | {cell(row.get('name') or row.get('to'))} | {number(row['distance_km'])} km | {number(row['duration_min']) if row.get('duration_min') is not None else 'nezjištěno'} min |"
            )
        lines.extend(
            [
                "",
                "Jde o nejrychlejší automobilové trasy OSRM a modelové časy bez živé dopravy. Nejde o pěší vzdálenost ani ověření bezpečnosti cesty do školy.",
            ]
        )
    smallest = min(parcels, key=lambda key: parcels[key]["area_m2"])
    largest = max(parcels, key=lambda key: parcels[key]["area_m2"])
    difference = parcels[largest]["area_m2"] - parcels[smallest]["area_m2"]
    lines.extend(
        [
            "",
            "### Rozdíly a kompromisy",
            "",
            f"Parcela {labels[largest]} má o {number(difference)} m² větší celkovou výměru než parcela {labels[smallest]}. Výměra ale není volná plocha: neříká, kolik místa zbývá pro zahradu, parkování nebo novou stavbu.",
            "Rodina může porovnat doloženou celkovou výměru a naměřený dojezd. Z těchto ukazatelů samotných nelze určit vhodnost parcely pro bydlení ani kvalitu školy.",
            "",
            "### Co zatím nevíme",
            "",
            "- Volná a zastavěná plocha, podoba a technický stav případné stavby.",
            "- Přípustné využití podle územního plánu, povolení a úplná omezení konkrétního záměru.",
            "- Dostupnost a kapacita sítí, kapacita školy, aktuální provoz zařízení a bezpečnost pěší trasy.",
            "",
            "Katastrální druh pozemku ani orientační prostorové kontroly nepotvrzují možnost výstavby. Shrnutí používá pouze vrácené datové výběry.",
        ]
    )
    sources = list(
        {
            json.dumps(source, sort_keys=True): source for item in items for source in item.sources
        }.values()
    )[:8]
    artifact = remember(
        {
            "title": "Ověřené porovnání parcel",
            "view": "bar",
            "label_key": "name",
            "value_key": "area_m2",
            "columns": [
                {"key": "name", "label": "Parcela"},
                {
                    "key": "area_m2",
                    "label": "Celková výměra",
                    "numeric": True,
                    "additive": True,
                    "unit": "m²",
                },
                {"key": "land_type", "label": "Katastrální druh"},
            ],
            "rows": [dict(row, name=labels[key]) for key, row in parcels.items()],
            "sources": sources,
            "sample": any(item.sample for item in items),
            "note": "Celková výměra není nezastavěná plocha ani stavební povolení.",
        },
        user_id,
    )
    return "\n".join(lines), artifact


def requested_comparison_reference(question, results):
    """An explicit follow-up summary of an already prepared parcel comparison."""
    if not re.search(
        r"\b(?:shr[nň]\w*|souhrn\w*|závěr\w*|summari\w*)\b", question, re.IGNORECASE
    ) or not re.search(r"parcel|porovn", question, re.IGNORECASE):
        return None
    if re.search(r"nové téma|new topic", question, re.IGNORECASE):
        return None
    if not re.search(r"parcel", question, re.IGNORECASE) and re.search(
        r"měst|obc|obyvatel|statistik|graf", question, re.IGNORECASE
    ):
        return None
    for key, item in reversed(list(results.items())):
        if 2 <= len(item.rows) <= 6 and all(
            str(row.get("id", "")).startswith("parcela:")
            and row.get("assessment_kind") == "indicative"
            for row in item.rows
        ):
            return key
    return None


def repair_tool_links(text, results, artifacts):
    """Recover model presentation links only from user-owned verified references."""
    displays = list(artifacts)

    def replace(match):
        label, operation, query = match.groups()
        reference = parse_qs(query).get("result_id", [None])[0]
        item = results.get(reference)
        if item is None:
            return label + " (výsledek vypršel nebo není dostupný)"
        view = {"show_map": "map", "show_table": "table", "show_chart": "auto"}[operation]
        intent = {"result_id": reference, "view": view}
        if operation == "show_chart":
            numeric = next((col.key for col in item.columns if col.numeric), None)
            caption = next((col.key for col in item.columns if not col.numeric), None)
            intent.update(value_key=numeric, label_key=caption)
        try:
            shown = present(intent, results)
        except ValueError:
            return label + " (požadované zobrazení nemá potřebná data)"
        if (
            not any((a.result_id, a.view) == (shown.result_id, shown.view) for a in displays)
            and len(displays) < 12
        ):
            displays.append(shown)
        return label

    cleaned = re.sub(r"\[([^\]]+)\]\((show_map|show_table|show_chart)\?([^)]*)\)", replace, text)
    return cleaned, displays


def fallback_answer(items):
    """Describe visible verified values when the provider returns no final prose."""
    if not items:
        return "K dotazu nejsou k dispozici ověřené výsledky."
    selected = items[-3:]
    sections = []
    for item in selected:
        lines = [f"### {item.title}"]
        if len(item.rows) == 1:
            row = item.rows[0]
            for col in item.columns:
                value = row.get(col.key)
                if value is None:
                    display = "neověřeno"
                elif isinstance(value, bool):
                    display = "ano" if value else "ne"
                elif isinstance(value, (int, float)):
                    display = (
                        f"{value:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")
                    )
                else:
                    display = str(value).replace("\n", " ")
                lines.append(
                    f"- **{col.label}:** {display}{' ' + col.unit if value is not None and col.unit else ''}"
                )
        else:
            lines.append(
                f"Zobrazuji {len(item.rows)} datových řádků"
                + (f" a {len(item.features)} mapových prvků." if item.features else ".")
            )
        if item.note:
            lines.extend(["", item.note])
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
