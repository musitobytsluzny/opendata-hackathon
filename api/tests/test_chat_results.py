"""Presentation references are scoped to a user and cannot invent data."""

import unittest
from unittest.mock import patch

from app.services import chat_results as results


class ChatResultTests(unittest.TestCase):
    def setUp(self):
        results._cache.clear()
        self.addCleanup(results._cache.clear)
        self.data = {
            "title": "Fixture",
            "columns": [
                {"key": "name", "label": "Obec"},
                {"key": "value", "label": "Počet", "numeric": True},
            ],
            "rows": [
                {"id": "obec:1", "name": "A", "value": 2},
                {"id": "obec:2", "name": "B", "value": 9},
            ],
            "features": [
                {
                    "type": "Feature",
                    "id": "obec:1",
                    "geometry": {"type": "Point", "coordinates": [13, 49]},
                    "properties": {},
                }
            ],
        }

    def test_user_isolation_and_expiry(self):
        with patch.object(results.time, "monotonic", return_value=100):
            item = results.remember(self.data, 1)
        with patch.object(results.time, "monotonic", return_value=101):
            self.assertFalse(results.restore([item.result_id], 2))
        with patch.object(results.time, "monotonic", return_value=101):
            self.assertIn(item.result_id, results.restore([item.result_id], 1))
        with patch.object(results.time, "monotonic", return_value=100 + results.TTL + 1):
            self.assertFalse(results.restore([item.result_id], 1))

    def test_chart_reuses_values_and_rejects_unknown_columns(self):
        item = results.remember(self.data, 1)
        context = {item.result_id: item}
        chart = results.present(
            {"result_id": item.result_id, "view": "bar", "value_key": "value", "label_key": "name"},
            context,
        )
        self.assertEqual(chart.rows, item.rows)
        with self.assertRaises(ValueError):
            results.present(
                {
                    "result_id": item.result_id,
                    "view": "bar",
                    "value_key": "invented",
                    "label_key": "name",
                },
                context,
            )
        with self.assertRaises(ValueError):
            results.present({"result_id": "invented", "view": "map"}, context)
        self.assertNotIn("features", results.model_context(item))

    def test_filter_does_not_retain_unselected_geometry(self):
        item = results.remember(self.data, 1)
        filtered = results.transform(
            {"result_id": item.result_id, "sort_key": "value", "limit": 1},
            {item.result_id: item},
            1,
        )
        self.assertEqual(filtered.rows[0]["value"], 9)
        self.assertFalse(filtered.features)
        self.assertEqual(item.rows[0]["value"], 2)

    def test_comparison_preserves_units_and_verified_values(self):
        first = results.remember(self.data, 1)
        second = results.remember(dict(self.data, rows=[{"name": "C", "value": 12}]), 1)
        context = {item.result_id: item for item in (first, second)}
        compared = results.combine({"result_ids": list(context)}, context, 1)
        self.assertEqual([row["value"] for row in compared.rows], [2, 9, 12])
        total = results.aggregate(
            {"result_id": compared.result_id, "value_key": "value", "operation": "sum"},
            {compared.result_id: compared},
            1,
        )
        self.assertEqual(total.rows[0]["value"], 23)
        self.assertIn("nikoliv z celé databáze", total.note)
        second.columns[1].unit = "km"
        with self.assertRaises(ValueError):
            results.combine({"result_ids": list(context)}, context, 1)

    def test_auto_chart_uses_comparison_bars_and_ordered_time_lines(self):
        item = results.remember(self.data, 1)
        intent = {
            "result_id": item.result_id,
            "view": "auto",
            "value_key": "value",
            "label_key": "name",
        }
        self.assertEqual(results.present(intent, {item.result_id: item}).view, "bar")
        item.columns[0].key = "year"
        item.rows = [{"year": "2024", "value": 2}, {"year": "2025", "value": 9}]
        intent["label_key"] = "year"
        self.assertEqual(results.present(intent, {item.result_id: item}).view, "line")

    def test_pie_requires_additive_nonnegative_values(self):
        item = results.remember(self.data, 1)
        intent = {
            "result_id": item.result_id,
            "view": "pie",
            "value_key": "value",
            "label_key": "name",
        }
        with self.assertRaises(ValueError):
            results.present(intent, {item.result_id: item})
        item.columns[1].additive = True
        self.assertEqual(results.present(intent, {item.result_id: item}).view, "pie")
        item.rows[0]["value"] = -1
        with self.assertRaises(ValueError):
            results.present(intent, {item.result_id: item})
