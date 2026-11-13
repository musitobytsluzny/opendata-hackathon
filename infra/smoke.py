"""Integration checks against the running dev stack, using only Python stdlib."""
import json
import os
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

# Verify the public SSE message URL and a full MCP initialize round trip.
with urlopen(Request(base + "/mcp/sse", headers={"Accept": "text/event-stream"}), timeout=10) as stream:
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
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "infra-smoke", "version": "1"}},
    }
    request = Request(urljoin(base, endpoint), data=json.dumps(message).encode(),
                      headers={"Content-Type": "application/json"})
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

print(f"OK: web, SPA fallback, API, DB {extensions}, MCP SSE initialize")
