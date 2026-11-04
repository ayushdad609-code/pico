"""
Unit tests for Pico's Interactive Browser Handoff and Session Vault.
From YOUR_FRIEND_FULL_SETUP.pdf (§12 Cloud Browser Agent Hand #2).
"""

import os
import shutil
import pytest
from pico.browser_handoff import SessionVault, BrowserHandoffEngine


@pytest.fixture
def temp_vault(tmp_path):
    vault_dir = str(tmp_path / "sessions")
    vault = SessionVault(storage_dir=vault_dir)
    yield vault
    if os.path.exists(vault_dir):
        shutil.rmtree(vault_dir)


def test_session_vault_save_load(temp_vault):
    cookies = [
        {"name": "session_id", "value": "test_token_abc123", "domain": "github.com"},
        {"name": "logged_in", "value": "yes", "domain": "github.com"}
    ]
    path = temp_vault.save_session("github.com", cookies, "https://github.com/login")
    assert os.path.exists(path)

    loaded = temp_vault.load_session("github.com")
    assert len(loaded) == 2
    assert loaded[0]["name"] == "session_id"
    assert loaded[0]["value"] == "test_token_abc123"

    sessions = temp_vault.list_sessions()
    assert "github.com" in sessions
    assert sessions["github.com"]["cookie_count"] == 2

    # Test deletion
    deleted = temp_vault.delete_session("github.com")
    assert deleted is True
    assert temp_vault.load_session("github.com") == []


def test_engine_init():
    engine = BrowserHandoffEngine(cdp_port=9222, web_port=8765)
    assert engine.cdp_port == 9222
    assert engine.web_port == 8765
    assert engine.vault is not None


@pytest.mark.anyio
async def test_engine_takeover_and_screencast():
    import aiohttp
    engine = BrowserHandoffEngine(cdp_port=9222, web_port=8766)
    try:
        res = await engine.start_takeover("https://example.com")
        assert res["success"] is True

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect("http://127.0.0.1:8766/ws/stream") as ws:
                frame_found = False
                for _ in range(8):
                    msg = await ws.receive_json(timeout=3.0)
                    if msg.get("type") == "frame":
                        frame_found = True
                        break
                assert frame_found is True

                await ws.send_json({"type": "click", "x": 100, "y": 100})
                await ws.send_json({"type": "type", "text": "hello"})
                await ws.send_json({"type": "done"})

                done_ack = False
                for _ in range(8):
                    ack = await ws.receive_json(timeout=3.0)
                    if ack.get("type") == "done_ack":
                        done_ack = True
                        break
                assert done_ack is True
    finally:
        await engine.cleanup()
