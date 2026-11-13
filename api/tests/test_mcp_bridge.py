"""Live local MCP -> API authentication checks, without calling Gemini."""

import json
import unittest
import uuid

from app.database.connection import SessionLocal, settings
from app.models import Profile, User
from app.schemas.user import UserCreate
from app.services.auth_service import create_access_token
from app.services.user_service import create_user
from mcp.client.sse import sse_client
from sqlalchemy import delete

from mcp import ClientSession


class MCPBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorization_reaches_data_api(self):
        with SessionLocal() as db:
            user = create_user(
                db,
                UserCreate(
                    username="mcp-test-" + uuid.uuid4().hex[:12],
                    password="Mcp-test-password",
                    profile={"firstname": "MCP", "lastname": "Test"},
                ),
            )
            user_id = user.id
            token = create_access_token(user.id, user.username)
        try:
            for authorization, expected in (({}, 401), ({"Authorization": "Bearer " + token}, 200)):
                async with sse_client(settings.mcp_server_url, headers=authorization) as (
                    read,
                    write,
                ):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = (await session.list_tools()).tools
                        tool = next(tool for tool in tools if tool.name == "dataset_catalog")
                        self.assertNotIn("ctx", tool.inputSchema.get("properties", {}))
                        result = await session.call_tool("dataset_catalog", {})
                        payload = result.structuredContent or json.loads(result.content[0].text)
                        if expected == 401:
                            self.assertEqual(payload["status"], 401)
                        else:
                            self.assertIn("datasets", payload)
        finally:
            with SessionLocal.begin() as db:
                db.execute(delete(Profile).where(Profile.user_id == user_id))
                db.execute(delete(User).where(User.id == user_id))
