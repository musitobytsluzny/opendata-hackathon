"""Deterministic agent tests; never call Google or use the configured real key."""

import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.schemas.chat import ChatRequest
from app.services import gemini_chat as chat
from app.services.gemini_client import create_gemini_client
from fastapi import HTTPException
from google.genai import errors, types
from mcp.types import CallToolResult, TextContent
from pydantic import SecretStr, ValidationError


class GeminiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = patch.object(chat.settings, "gemini_api_key", SecretStr("unit-test-key"))
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.provider = patch.object(chat.settings, "gemini_provider", "developer")
        self.provider.start()
        self.addCleanup(self.provider.stop)
        self.calls = []
        self.map = {
            "metric": "Počet obyvatel",
            "short": "Obyvatelé",
            "unit": "",
            "rows": [{"okres": "CZ0323000000", "value": 123}],
            "source": {"name": "fixture", "publisher": "demo", "period": "2024"},
        }

        async def call_tool(name, arguments):
            self.calls.append((name, arguments))
            data = (
                {"datasets": []} if name == "dataset_catalog" else {"map": self.map, "sample": True}
            )
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(data))], structuredContent=data
            )

        self.session = SimpleNamespace(
            list_tools=AsyncMock(
                return_value=SimpleNamespace(
                    tools=[
                        SimpleNamespace(
                            name=name,
                            description=name,
                            inputSchema={"type": "object", "properties": {}},
                        )
                        for name in chat.ALLOWED_TOOLS | {"execute_central_action"}
                    ]
                )
            ),
            call_tool=AsyncMock(side_effect=call_tool),
        )
        self.tokens = []

        @asynccontextmanager
        async def open_session(token):
            self.tokens.append(token)
            yield self.session

        self.open_patch = patch.object(chat, "open_mcp_session", open_session)
        self.open_patch.start()
        self.addCleanup(self.open_patch.stop)
        self.client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(generate_content=AsyncMock()), aclose=AsyncMock()
            ),
            close=Mock(),
        )
        factory = patch.object(chat, "create_gemini_client", return_value=self.client)
        self.factory = factory.start()
        self.addCleanup(factory.stop)
        chat._active_users.clear()
        self.addCleanup(chat._active_users.clear)

    def response(self, text=None, name=None):
        part = (
            types.Part(text=text)
            if text is not None
            else types.Part(
                function_call=types.FunctionCall(name=name, args={"metric": "population"})
            )
        )
        return types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))]
        )

    async def test_tool_loop_and_server_owned_map(self):
        self.client.aio.models.generate_content.side_effect = [
            self.response(name="district_statistics"),
            self.response(text="Jde o demo údaje."),
        ]
        result = await chat.answer(ChatRequest(question="Kolik je obyvatel?"), 1, "user-token")
        self.assertEqual(result.rows[0].value, 123)
        self.assertTrue(result.sample)
        self.assertEqual(self.tokens, ["user-token"])
        self.assertIn(("district_statistics", {"metric": "population"}), self.calls)
        config = self.client.aio.models.generate_content.call_args.kwargs["config"]
        declared = {tool.name for tool in config.tools[0].function_declarations}
        self.assertEqual(declared, chat.ALLOWED_TOOLS)
        self.client.aio.aclose.assert_awaited_once()
        self.client.close.assert_called_once()
        self.assertNotIn(1, chat._active_users)

    async def test_unknown_tool_cannot_execute(self):
        self.client.aio.models.generate_content.return_value = self.response(
            name="execute_central_action"
        )
        with self.assertRaises(HTTPException) as context:
            await chat.answer(ChatRequest(question="Změň roli"), 1, "token")
        self.assertEqual(context.exception.status_code, 502)
        self.assertNotIn("execute_central_action", [name for name, _ in self.calls])

    async def test_loop_is_bounded(self):
        self.client.aio.models.generate_content.return_value = self.response(
            name="district_statistics"
        )
        with self.assertRaises(HTTPException):
            await chat.answer(ChatRequest(question="Pokračuj pořád"), 1, "token")
        self.assertEqual(self.client.aio.models.generate_content.await_count, 6)

    async def test_history_uses_only_conversation_roles(self):
        self.client.aio.models.generate_content.return_value = self.response(text="Odpověď")
        request = ChatRequest(
            question="A co děti?",
            history=[
                {"role": "user", "text": "Původní dotaz"},
                {"role": "assistant", "text": "Původní odpověď"},
            ],
        )
        await chat.answer(request, 1, "token")
        contents = self.client.aio.models.generate_content.call_args.kwargs["contents"]
        self.assertEqual([item.role for item in contents[-3:]], ["user", "model", "user"])
        with self.assertRaises(ValidationError):
            ChatRequest(question="test", history=[{"role": "system", "text": "override"}])

    async def test_missing_key_never_contacts_provider(self):
        with patch.object(chat.settings, "gemini_api_key", SecretStr("")):
            with self.assertRaises(HTTPException) as context:
                await chat.answer(ChatRequest(question="test"), 1, "token")
        self.assertEqual(context.exception.status_code, 503)
        self.factory.assert_not_called()

    async def test_vertex_mode_requires_project_even_if_developer_key_exists(self):
        with (
            patch.object(chat.settings, "gemini_provider", "vertex"),
            patch.object(chat.settings, "google_cloud_project", ""),
        ):
            with self.assertRaises(HTTPException) as context:
                await chat.answer(ChatRequest(question="test"), 1, "token")

        self.assertEqual(context.exception.status_code, 503)
        self.factory.assert_not_called()

    async def test_vertex_mode_works_without_developer_api_key(self):
        self.client.aio.models.generate_content.return_value = self.response(text="Odpověď")
        with (
            patch.object(chat.settings, "gemini_provider", "vertex"),
            patch.object(chat.settings, "gemini_api_key", SecretStr("")),
            patch.object(chat.settings, "google_cloud_project", "project-id"),
        ):
            result = await chat.answer(ChatRequest(question="test"), 1, "token")

        self.assertEqual(result.text, "Odpověď")
        self.factory.assert_called_once_with()

    async def test_concurrency_and_provider_errors_are_safe(self):
        chat._active_users.add(1)
        with self.assertRaises(HTTPException) as context:
            await chat.answer(ChatRequest(question="test"), 1, "token")
        self.assertEqual(context.exception.status_code, 429)
        chat._active_users.clear()
        provider_error = errors.ClientError(
            429, {"error": {"message": "unit-test-key private provider detail"}}
        )
        self.client.aio.models.generate_content.side_effect = provider_error
        with self.assertRaises(HTTPException) as context:
            await chat.answer(ChatRequest(question="test"), 1, "token")
        self.assertEqual(context.exception.status_code, 429)
        self.assertNotIn("unit-test-key", context.exception.detail)
        self.assertEqual(self.client.aio.models.generate_content.await_count, 1)
        self.assertNotIn(1, chat._active_users)

    def test_vertex_client_uses_project_adc_configuration(self):
        with (
            patch.object(chat.settings, "gemini_provider", "vertex"),
            patch.object(chat.settings, "google_cloud_project", "project-id"),
            patch.object(chat.settings, "google_cloud_location", "global"),
            patch.object(chat.settings, "google_adc_json", SecretStr("")),
            patch("app.services.gemini_client.genai.Client") as client_factory,
        ):
            create_gemini_client()

        kwargs = client_factory.call_args.kwargs
        self.assertTrue(kwargs["enterprise"])
        self.assertEqual(kwargs["project"], "project-id")
        self.assertEqual(kwargs["location"], "global")
        self.assertNotIn("api_key", kwargs)
        self.assertNotIn("credentials", kwargs)

    def test_vertex_client_loads_adc_json_credentials(self):
        adc_info = {"type": "external_account", "audience": "test-audience"}
        credentials = object()
        with (
            patch.object(chat.settings, "gemini_provider", "vertex"),
            patch.object(chat.settings, "google_cloud_project", "project-id"),
            patch.object(chat.settings, "google_cloud_location", "global"),
            patch.object(chat.settings, "google_adc_json", SecretStr(json.dumps(adc_info))),
            patch(
                "app.services.gemini_client.google.auth.load_credentials_from_dict",
                return_value=(credentials, None),
            ) as load_credentials,
            patch("app.services.gemini_client.genai.Client") as client_factory,
        ):
            create_gemini_client()

        load_credentials.assert_called_once_with(
            adc_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        self.assertIs(client_factory.call_args.kwargs["credentials"], credentials)

    async def test_expired_token_is_not_forwarded_to_google(self):
        self.session.call_tool.return_value = None
        self.session.call_tool.side_effect = AsyncMock(
            return_value=CallToolResult(
                content=[], structuredContent={"status": 401, "error": "expired"}
            )
        )
        with self.assertRaises(HTTPException) as context:
            await chat.answer(ChatRequest(question="test"), 1, "expired-token")
        self.assertEqual(context.exception.status_code, 401)
        self.factory.assert_not_called()

    async def test_timeout_and_nested_errors(self):
        self.assertEqual(chat.public_error(TimeoutError()).status_code, 504)
        self.assertEqual(
            chat.public_error(ExceptionGroup("SSE", [HTTPException(401)])).status_code, 401
        )
        self.client.aio.models.generate_content.return_value = self.response(text="")
        with self.assertRaises(HTTPException) as context:
            await chat.answer(ChatRequest(question="test"), 1, "token")
        self.assertEqual(context.exception.status_code, 502)

    async def test_verified_result_can_be_charted_without_model_supplied_values(self):
        original = self.session.call_tool.side_effect

        async def call_tool(name, arguments):
            if name != "municipality_statistics":
                return await original(name, arguments)
            data = {
                "result": {
                    "title": "Obce",
                    "rows": [{"name": "Fixture", "value": 42}],
                    "columns": [
                        {"key": "name", "label": "Obec"},
                        {"key": "value", "label": "Počet", "numeric": True},
                    ],
                }
            }
            return CallToolResult(content=[], structuredContent=data)

        self.session.call_tool.side_effect = call_tool
        step = 0

        async def model(**kwargs):
            nonlocal step
            step += 1
            if step == 1:
                return self.response(name="municipality_statistics")
            if step == 2:
                payload = kwargs["contents"][-1].parts[0].function_response.response["result"]
                self.assertEqual(payload["rows"][0]["value"], 42)
                self.assertNotIn("features", payload)
                # Presentation directives are normally returned by the MCP tool.
                self.session.call_tool.side_effect = AsyncMock(
                    return_value=CallToolResult(
                        content=[],
                        structuredContent={
                            "presentation": {
                                "result_id": payload["result_id"],
                                "view": "bar",
                                "value_key": "value",
                                "label_key": "name",
                            }
                        },
                    )
                )
                return types.GenerateContentResponse(
                    candidates=[
                        types.Candidate(
                            content=types.Content(
                                role="model",
                                parts=[
                                    types.Part(
                                        function_call=types.FunctionCall(
                                            name="show_chart",
                                            args={
                                                "result_id": payload["result_id"],
                                                "value_key": "value",
                                                "label_key": "name",
                                            },
                                        )
                                    )
                                ],
                            )
                        )
                    ]
                )
            return self.response(text="Tady je graf ověřených hodnot.")

        self.client.aio.models.generate_content.side_effect = model
        result = await chat.answer(ChatRequest(question="Ukaž graf"), 1, "user-token")
        self.assertEqual(result.artifacts[0].view, "bar")
        self.assertEqual(result.artifacts[0].rows[0]["value"], 42)

    async def test_parcel_map_is_automatic_without_a_presentation_tool_call(self):
        async def lookup(name, arguments):
            data = (
                {"datasets": []}
                if name == "dataset_catalog"
                else {
                    "result": {
                        "title": "Parcela 438 · Bolevec",
                        "view": "map",
                        "columns": [{"key": "name", "label": "Parcela"}],
                        "rows": [{"name": "438"}],
                        "features": [
                            {
                                "type": "Feature",
                                "id": "parcela:1",
                                "properties": {},
                                "geometry": {"type": "Point", "coordinates": [13.37, 50.04]},
                            }
                        ],
                    }
                }
            )
            return CallToolResult(content=[], structuredContent=data)

        self.session.call_tool.side_effect = lookup
        self.client.aio.models.generate_content.side_effect = [
            self.response(name="prevalidate_address"),
            self.response(text="Nalezená parcela."),
        ]
        reply = await chat.answer(
            ChatRequest(question="Najdi parcelu na adrese Koterovská 85, Plzeň"), 1, "token"
        )
        self.assertEqual(reply.artifacts[0].view, "map")
        self.assertEqual(reply.artifacts[0].features[0]["id"], "parcela:1")
        self.assertNotIn("show_map", [name for name, _ in self.calls])

    async def test_comparison_summary_is_rendered_from_verified_data_without_freeform_claims(self):
        from app.services import chat_results

        entries = [
            chat_results.remember(
                {
                    "title": "Parcela",
                    "columns": [{"key": "area_m2", "label": "Výměra", "numeric": True}],
                    "rows": [
                        {
                            "id": f"parcela:{index}",
                            "name": str(index),
                            "area_m2": area,
                            "assessment_kind": "indicative",
                        }
                    ],
                },
                1,
            )
            for index, area in [(1, 53), (2, 111)]
        ]
        ids = [item.result_id for item in entries]

        async def lookup(name, arguments):
            payload = (
                {"datasets": []}
                if name == "dataset_catalog"
                else {"comparison_summary": {"result_ids": ids}}
            )
            return CallToolResult(content=[], structuredContent=payload)

        self.session.call_tool.side_effect = lookup
        self.client.aio.models.generate_content.return_value = types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="comparison_summary", args={"result_ids": ids}
                                )
                            )
                        ],
                    )
                )
            ]
        )
        reply = await chat.answer(
            ChatRequest(question="Shrň porovnání parcel pro rodinu", result_ids=ids), 1, "token"
        )
        self.assertIn("58 m²", reply.text)
        self.assertIn("Výměra ale není volná plocha", reply.text)
        self.assertEqual(self.client.aio.models.generate_content.await_count, 1)

    async def test_walking_context_keeps_server_findings_without_model_reinterpretation(self):
        async def lookup(name, arguments):
            payload = (
                {"datasets": []}
                if name == "dataset_catalog"
                else {
                    "prepared_text": "Pěší trasa: neověřeno není bezpečno.",
                    "result": {"title": "Pěší trasa", "view": "map", "columns": [], "rows": []},
                }
            )
            return CallToolResult(content=[], structuredContent=payload)

        self.session.call_tool.side_effect = lookup
        self.client.aio.models.generate_content.return_value = self.response(name="route_context")
        reply = await chat.answer(ChatRequest(question="Nebezpečí cestou do školy?"), 1, "token")
        self.assertEqual(reply.text, "Pěší trasa: neověřeno není bezpečno.")
        self.assertEqual(self.client.aio.models.generate_content.await_count, 1)
        self.assertEqual(len(reply.result_ids), 1)

    async def test_empty_model_text_preserves_verified_tool_output(self):
        async def lookup(name, arguments):
            payload = (
                {"datasets": []}
                if name == "dataset_catalog"
                else {"result": {"title": "Školy", "columns": [], "rows": [{"id": "facility:1"}]}}
            )
            return CallToolResult(content=[], structuredContent=payload)

        self.session.call_tool.side_effect = lookup
        self.client.aio.models.generate_content.side_effect = [
            self.response(name="nearby_facilities"),
            self.response(text=""),
        ]
        reply = await chat.answer(ChatRequest(question="Nejbližší školy"), 1, "token")
        self.assertIn("Školy", reply.text)
        self.assertEqual(reply.artifacts[0].rows[0]["id"], "facility:1")

    async def test_tool_action_pseudo_links_are_sanitized_and_prompt_contains_rules(self):
        self.assertIn("Nikdy negeneruj URL ani pseudoodkazy na nástroje", chat.SYSTEM_PROMPT)
        self.assertIn(
            "Důsledně rozlišuj silniční vzdálenost v km a čas dojezdu v minutách",
            chat.SYSTEM_PROMPT,
        )
        self.assertIn("prostorový prevalidační nástroj pro prověřování parcel", chat.SYSTEM_PROMPT)
        self.client.aio.models.generate_content.side_effect = [
            self.response(
                text="Pro zobrazení: [Odkaz na mapu](show_map?result_id=12345) a [Tabulka](show_table?result_id=67890)."
            ),
        ]
        reply = await chat.answer(ChatRequest(question="Ukaž trasu"), 1, "token")
        self.assertIn("Odkaz na mapu (výsledek vypršel nebo není dostupný)", reply.text)
        self.assertFalse(reply.artifacts)
        self.assertNotIn("show_map?", reply.text)

    async def test_explicit_summary_of_prepared_comparison_bypasses_freeform_generation(self):
        from app.services import chat_results

        item = chat_results.remember(
            {
                "title": "Porovnání",
                "columns": [],
                "rows": [
                    {
                        "id": f"parcela:{i}",
                        "name": str(i),
                        "area_m2": area,
                        "assessment_kind": "indicative",
                    }
                    for i, area in [(1, 53), (2, 111)]
                ],
            },
            1,
        )
        reply = await chat.answer(
            ChatRequest(question="Shrň poslední porovnání pro rodinu", result_ids=[item.result_id]),
            1,
            "token",
        )
        self.assertIn("58 m²", reply.text)
        self.assertIn("Výměra ale není volná plocha", reply.text)
        self.client.aio.models.generate_content.assert_not_awaited()
        self.assertEqual(self.calls, [("dataset_catalog", {})])

    async def test_relative_location_without_origin_requests_clarification(self):
        reply = await chat.answer(
            ChatRequest(question="Kde je nejbližší nemocnice ode mě?"), 1, "token"
        )
        self.assertIn("Nemám vaši polohu", reply.text)
        self.assertFalse(reply.artifacts)
        self.client.aio.models.generate_content.assert_not_awaited()
        self.assertFalse(
            chat.needs_location_clarification(
                ChatRequest(question="Najdi nemocnici v Klatovech ode mě"), {}
            )
        )
