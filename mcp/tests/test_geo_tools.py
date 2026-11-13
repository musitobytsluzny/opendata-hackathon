import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from tools.geo_tools import _read


class GeoToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_user_token_is_scoped_to_its_request(self):
        received = []

        def handler(request):
            received.append(request.headers["Authorization"])
            return httpx.Response(200, json={"datasets": []})

        async with httpx.AsyncClient(
            base_url="http://api",
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer service-default"},
        ) as client:
            with patch(
                "tools.geo_tools.get_api_client", return_value=SimpleNamespace(client=client)
            ):

                def context(token):
                    return SimpleNamespace(
                        request_context=SimpleNamespace(
                            request=SimpleNamespace(headers={"authorization": "Bearer " + token})
                        )
                    )

                await asyncio.gather(
                    _read(context("user-a"), "/data/catalog"),
                    _read(context("user-b"), "/data/catalog"),
                )
            self.assertEqual(set(received), {"Bearer user-a", "Bearer user-b"})
            self.assertEqual(client.headers["Authorization"], "Bearer service-default")

    async def test_missing_user_token_cannot_use_service_identity(self):
        context = SimpleNamespace(request_context=SimpleNamespace(request=None))
        self.assertEqual((await _read(context, "/data/catalog"))["status"], 401)
