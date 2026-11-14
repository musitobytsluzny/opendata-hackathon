"""Bounded, user-scoped short-lived references to verified tool results."""

import json
import time
from collections import OrderedDict
from secrets import token_hex

from app.schemas.chat import ChatArtifact

_cache: OrderedDict[str, tuple[int, float, ChatArtifact]] = OrderedDict()
TTL = 900


def remember(payload, user_id):
    if len(json.dumps(payload, ensure_ascii=False)) > 450000:
        raise ValueError("Výsledek je příliš velký; zmenši oblast nebo počet prvků.")
    artifact = ChatArtifact.model_validate(dict(payload, result_id=token_hex(12)))
    _cache[artifact.result_id] = (user_id, time.monotonic(), artifact)
    while len(_cache) > 128:
        _cache.popitem(last=False)
    return artifact


def restore(ids, user_id):
    results = {}
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
    rows = sorted(values, key=lambda row: row[key], reverse=bool(intent.get("descending", True)))[
        :limit
    ]
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
