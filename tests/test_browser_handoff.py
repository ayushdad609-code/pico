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
