"""
Tests for Pico REST API Endpoints without external plugins.
"""

import asyncio
import json
from aiohttp.test_utils import make_mocked_request
from pico.api import PicoServer


def test_api_health_endpoint():
    async def _test():
        server = PicoServer(":memory:")
        req = make_mocked_request("GET", "/api/health")
        resp = await server.health_check(req)
        assert resp.status == 200
        data = json.loads(resp.body.decode("utf-8"))
        assert data["status"] == "healthy"
        assert data["friend_name"] == "Pico"
    asyncio.run(_test())


def test_api_what_i_know_endpoint():
    async def _test():
        server = PicoServer(":memory:")
        req = make_mocked_request("GET", "/api/what-i-know")
        resp = await server.handle_what_i_know(req)
        assert resp.status == 200
        data = json.loads(resp.body.decode("utf-8"))
        assert "facts" in data
    asyncio.run(_test())


def test_api_artifacts_sip_endpoint():
    async def _test():
        server = PicoServer(":memory:")
        req = make_mocked_request("GET", "/api/artifacts/sip?amt=5000&cagr=15&years=26")
        resp = await server.handle_sip_artifact(req)
        assert resp.status == 200
        data = json.loads(resp.body.decode("utf-8"))
        assert data["primary"] == "₹1,91,25,123"
        assert "boring superpower" in data["his_line"].lower()
    asyncio.run(_test())


def test_api_tokens_endpoint():
    async def _test():
        server = PicoServer(":memory:")
        req = make_mocked_request("GET", "/api/tokens")
        resp = await server.handle_tokens(req)
        assert resp.status == 200
        data = json.loads(resp.body.decode("utf-8"))
        assert data["monthly_quota"] == 40_000_000
        assert data["is_low_power"] is False
    asyncio.run(_test())


def test_api_routine_day_path_endpoint():
    async def _test():
        server = PicoServer(":memory:")
        req = make_mocked_request("GET", "/api/path")
        resp = await server.handle_day_path(req)
        assert resp.status == 200
        data = json.loads(resp.body.decode("utf-8"))
        assert "day_path" in data
        assert len(data["day_path"]) >= 5
    asyncio.run(_test())
