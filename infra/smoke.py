"""Integration checks against the running dev stack, using only Python stdlib."""

import base64
import json
import os
import uuid
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

base = os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")


def get(path):
    with urlopen(base + path, timeout=10) as response:
        return response.read()


assert b"/src/main.tsx" in get("/")
assert b"/src/main.tsx" in get("/some/spa/route")
assert json.loads(get("/api/health"))["status"] == "ok"
extensions = json.loads(get("/api/health/db"))["extensions"]
assert set(extensions) == {"postgis", "vector"}, extensions
schema = json.loads(get("/api/openapi.json"))
assert schema["servers"][0]["url"] == "/api", schema.get("servers")
assert json.loads(get("/mcp/health"))["status"] == "ok"


def api(method, path, payload=None, status=200, token=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(
        base + "/api" + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        assert response.status == status, (method, path, response.status, body)
        return json.loads(body) if body else None


# Exercise the merged API contract used by the frontend, then remove our user.
username = "sync-smoke-" + uuid.uuid4().hex[:12]
password = "Smoke-password-" + uuid.uuid4().hex
registration = {
    "username": username,
    "password": password,
    "profile": {"firstname": "Smoke", "lastname": "Test"},
}
user = api("POST", "/users/", registration, 201)
try:
    api("POST", "/users/", registration, 409)
    api("POST", "/auth/login", {"username": username, "password": "wrong"}, 401)
    login = api("POST", "/auth/login", {"username": username, "password": password})
    assert login["token_type"] == "bearer"
    token = login["access_token"]
    assert api("GET", "/auth/me", token=token)["id"] == user["id"]
    api("GET", "/auth/me", status=401)
    api("GET", "/auth/me", status=401, token="invalid.jwt.signature")
    api("POST", "/chat/ask", {"question": "Test"}, 401)
    api("POST", "/chat/ask", {"question": "   "}, 422, token=token)
    unavailable = api("POST", "/chat/ask", {"question": "Kolik je obyvatel?"}, 503, token=token)
    assert "Datové zdroje" in unavailable["detail"]
    segment = login["access_token"].split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
    assert claims["sub"] == str(user["id"]) and claims["username"] == username
    assert claims["exp"] > claims["iat"]
    assert api("GET", f"/users/{user['id']}")["username"] == username
    updated = api("PATCH", f"/users/{user['id']}", {"profile": {"firstname": "Updated"}})
    assert updated["profile"]["firstname"] == "Updated"
finally:
    api("DELETE", f"/users/{user['id']}", status=204)
api("GET", f"/users/{user['id']}", status=404)
api("GET", "/auth/me", status=401, token=token)

# Verify the public SSE message URL and a full MCP initialize round trip.
with urlopen(
    Request(base + "/mcp/sse", headers={"Accept": "text/event-stream"}), timeout=10
) as stream:
    event = ""
    endpoint = None
    for raw in stream:
        line = raw.decode().strip()
        if line.startswith("event:"):
            event = line[6:].strip()
        if event == "endpoint" and line.startswith("data:"):
            endpoint = line[5:].strip()
            break
    assert endpoint and endpoint.startswith("/mcp/messages/"), endpoint
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "infra-smoke", "version": "1"},
        },
    }
    request = Request(
        urljoin(base, endpoint),
        data=json.dumps(message).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=10) as response:
        assert response.status == 202
    for raw in stream:
        line = raw.decode().strip()
        if line.startswith("data:"):
            response = json.loads(line[5:])
            assert response.get("id") == 1 and "result" in response, response
            break
    else:
        raise AssertionError("SSE closed without initialize response")

print(f"OK: web, SPA fallback, API user CRUD + JWT login, DB {extensions}, MCP SSE initialize")
