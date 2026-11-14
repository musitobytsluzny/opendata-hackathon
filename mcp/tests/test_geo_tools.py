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

    async def test_registry_does_not_expose_generic_service_identity_actions(self):
        from mcp.server.fastmcp import FastMCP
        from resources import register_all_resources
        from tools import register_all_tools

        server = FastMCP("registry-audit")
        register_all_tools(server)
        register_all_resources(server)
        names = {tool.name for tool in await server.list_tools()}
        self.assertIn("dataset_catalog", names)
        self.assertIn("rank_driving_candidates", names)
        self.assertNotIn("execute_central_action", names)
        self.assertNotIn("search_datasets", names)
        self.assertEqual(await server.list_resources(), [])

    async def test_client_errors_preserve_recovery_hint_but_server_errors_do_not_leak(self):
        context = SimpleNamespace(
            request_context=SimpleNamespace(
                request=SimpleNamespace(headers={"authorization": "Bearer user"})
            )
        )
        for status, detail in [
            (422, "Tolerance musí být v rozmezí 0–1000 m."),
            (500, "private-server-stack"),
        ]:
            async with httpx.AsyncClient(
                base_url="http://api",
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(status, json={"detail": detail})
                ),
            ) as client:
                with patch(
                    "tools.geo_tools.get_api_client", return_value=SimpleNamespace(client=client)
                ):
                    payload = await _read(context, "/data/parcels/balanced")
            self.assertEqual(payload["status"], status)
            if status == 422:
                self.assertEqual(payload["error"], detail)
            else:
                self.assertNotIn(detail, payload["error"])
