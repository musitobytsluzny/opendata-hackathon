"""Deterministic agent tests; never call Google or use the configured real key."""

import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.schemas.chat import ChatRequest
from app.services import gemini_chat as chat
from fastapi import HTTPException
from google.genai import errors, types
from mcp.types import CallToolResult, TextContent
from pydantic import SecretStr, ValidationError


class GeminiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = patch.object(chat.settings, "gemini_api_key", SecretStr("unit-test-key"))
        self.settings.start()
        self.addCleanup(self.settings.stop)
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
        factory = patch.object(chat.genai, "Client", return_value=self.client)
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
        self.assertNotIn(1, chat._active_users)

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
