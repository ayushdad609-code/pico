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


def test_api_get_started_page_endpoint():
    async def _test():
        server = PicoServer(":memory:")
        req = make_mocked_request("GET", "/")
        resp = await server.handle_index(req)
        assert resp.status == 200
        assert resp.content_type == "text/html"
        html = resp.body.decode("utf-8")
        assert "GET STARTED" in html
        assert "pico_pointing_transparent.png" in html
        assert "duo-hero" in html
        assert "muse-chat-layout" in html
        assert "view-switcher" in html
        assert "connectors" in html
        assert "skills" in html
        assert "artifacts" in html
        assert "md files" in html
        assert "download" in html
        assert "schedule" in html
        assert "btn-pico-tasks" in html
        assert "task-dropdown" in html
        assert "● LIVE CALL SESSION" not in html
        assert "waiting for the barber opening confirmation call" not in html
        assert "CODING & TECH" not in html
        assert "Streaks keep you in the zone" not in html
        assert "Zero-surprise phone calls" not in html
        assert "A friend you can actually trust" not in html
        assert "Start your momentum today" not in html
        assert "About Us" not in html
        assert "panel-connectors" in html
        assert "panel-skills" in html
        assert "21st.dev" in html
        assert "v0 by Vercel" in html
        assert "panel-artifacts" in html
        assert "panel-mdfiles" in html
        assert "panel-schedule" in html
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


def test_api_telephony_twiml_endpoint():
    async def _test():
        server = PicoServer(":memory:")
        req = make_mocked_request("GET", "/api/telephony/twiml", headers={"Host": "api.pico.ai"})
        resp = await server.handle_twiml(req)
        assert resp.status == 200
        assert resp.content_type == "application/xml"
        body = resp.body.decode("utf-8")
        assert "<Response>" in body
        assert '<Stream url="ws://api.pico.ai/api/telephony/media-stream">' in body
    asyncio.run(_test())


def test_api_chrome_and_gmail_endpoints():
    async def _test():
        server = PicoServer(":memory:")

        # 1. Chrome Tabs GET
        req_chrome_get = make_mocked_request("GET", "/api/events/chrome")
        resp_chrome_get = await server.handle_chrome_tabs(req_chrome_get)
        assert resp_chrome_get.status == 200
        data_chrome = json.loads(resp_chrome_get.body.decode("utf-8"))
        assert data_chrome["tab_count"] == 0

        # 2. Chrome Tab POST
        req_chrome_post = make_mocked_request("POST", "/api/events/chrome")
        req_chrome_post._read_bytes = json.dumps({"url": "https://github.com/ayush/pico", "title": "Pico"}).encode("utf-8")
        resp_chrome_post = await server.handle_chrome_tab_post(req_chrome_post)
        assert resp_chrome_post.status == 200
        post_data = json.loads(resp_chrome_post.body.decode("utf-8"))
        assert post_data["success"] is True
        assert post_data["tab"]["domain"] == "github.com"

        # 3. Gmail GET (unconfigured)
        req_gmail = make_mocked_request("GET", "/api/events/gmail")
        resp_gmail = await server.handle_gmail_events(req_gmail)
        assert resp_gmail.status == 200
        data_gmail = json.loads(resp_gmail.body.decode("utf-8"))
        assert data_gmail["configured"] is False
    asyncio.run(_test())


def test_api_docs_endpoint():
    async def _test():
        server = PicoServer(":memory:")
        req = make_mocked_request("GET", "/api/docs/docs/pico_ui_brief.md", match_info={"filename": "docs/pico_ui_brief.md"})
        resp = await server.handle_get_doc(req)
        assert resp.status == 200
        data = json.loads(resp.body.decode("utf-8"))
        assert "Pico UI Design & Architecture Brief" in data["content"]
        assert data["filename"] == "docs/pico_ui_brief.md"

        # Traversal protection test
        req_bad = make_mocked_request("GET", "/api/docs/../../../etc/passwd", match_info={"filename": "../../../etc/passwd"})
        resp_bad = await server.handle_get_doc(req_bad)
        assert resp_bad.status in (403, 404)
    asyncio.run(_test())

