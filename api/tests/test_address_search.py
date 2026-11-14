"""Address formatting must not turn a valid postcode into an impossible name match."""

import unittest
from unittest.mock import patch

import httpx
from app.services import cuzk_client
from fastapi import HTTPException


class AddressSearchTests(unittest.TestCase):
    def test_postcode_with_or_without_space_is_a_numeric_filter(self):
        real_client = httpx.Client
        queries = []

        def respond(request):
            queries.append(request.url.params["where"])
            return httpx.Response(
                200,
                json={
                    "features": [
                        {
                            "attributes": {"adresa": "Žihle 294", "psc": 33165},
                            "geometry": {"x": 13.37, "y": 50.04},
                        }
                    ]
                },
            )

        with patch.object(
            cuzk_client.httpx,
            "Client",
            side_effect=lambda **kw: real_client(**kw, transport=httpx.MockTransport(respond)),
        ):
            for query in ["Žihle 294, 331 65", "Žihle 294, 33165", "33165 Žihle 294"]:
                self.assertEqual(len(cuzk_client.search_address(query=query)), 1)
        for where in queries:
            self.assertIn("psc = 33165", where)
            self.assertIn("cislodomovni = 294", where)
            self.assertNotIn("LIKE '%331", where)

    def test_upstream_error_is_not_reported_as_address_not_found(self):
        real_client = httpx.Client
        with patch.object(
            cuzk_client.httpx,
            "Client",
            side_effect=lambda **kw: real_client(
                **kw,
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"error": {"code": 500}})
                ),
            ),
        ):
            with self.assertRaises(HTTPException) as error:
                cuzk_client.search_address(query="Žihle 294")
        self.assertEqual(error.exception.status_code, 503)
