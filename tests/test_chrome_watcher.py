"""Tests for Chrome Tabs Watcher and Context Categorization."""

import pytest
from unittest.mock import AsyncMock, patch
from pico.chrome_watcher import (
    ChromeWatcher,
    ChromeTab,
    categorize_url
)
from pico.memory import MemoryStore

def test_categorize_url_and_topics():
    assert categorize_url("https://github.com/ayushdad609-code/pico", "GitHub Repo") == "Coding & Tech"
    assert categorize_url("https://tradingview.com/chart/nifty", "TradingView Chart") == "Finance & Markets"
    assert categorize_url("https://www.makemytrip.com/hotels/goa", "Hotels in Goa") == "Travel & Leisure"
    assert categorize_url("https://www.swiggy.com/restaurants", "Swiggy Food") == "Shopping & Food"
    assert categorize_url("https://mail.google.com/mail/u/0/#inbox", "Gmail Inbox") == "Productivity"


def test_chrome_watcher_record_and_summary():
    cw = ChromeWatcher()

    # Record 3 tabs
    t1 = cw.record_tab(url="https://github.com/ayush/pico", title="Pico Architecture")
    t2 = cw.record_tab(url="https://docs.python.org/3/library/imaplib.html", title="imaplib docs")
    t3 = cw.record_tab(url="https://tradingview.com", title="TradingView")

    tabs = cw.get_open_tabs()
    assert len(tabs) == 3
    assert tabs[0].domain == "github.com"
    assert tabs[0].category == "Coding & Tech"

    summary = cw.get_browsing_summary()
    assert summary["tab_count"] == 3
    assert summary["primary_category"] == "Coding & Tech"
    assert "github.com" in summary["top_domains"]


@pytest.mark.anyio
async def test_chrome_watcher_cdp_poll():
    cw = ChromeWatcher()

    # Mock response from http://127.0.0.1:9222/json/list
    mock_cdp_tabs = [
        {"id": "tab1", "title": "Python 3.14 Release Notes", "url": "https://docs.python.org/3.14/", "type": "page"},
        {"id": "tab2", "title": "Goa Hotel Sunrise Booking", "url": "https://booking.com/hotel-sunrise", "type": "page"}
    ]

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=mock_cdp_tabs)

    class MockContextManager:
        async def __aenter__(self):
            return mock_resp
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("aiohttp.ClientSession.get", return_value=MockContextManager()):
        tabs = await cw.poll_cdp_tabs("http://127.0.0.1:9222")
        assert len(tabs) == 2
        assert tabs[0].title == "Python 3.14 Release Notes"
        assert tabs[1].category == "Travel & Leisure"


def test_chrome_watcher_sync_to_memory():
    cw = ChromeWatcher()
    cw.record_tab("https://github.com/ayush/pico", "Building Pico Telephony")
    cw.record_tab("https://docs.python.org", "Python Docs")

    mem = MemoryStore(":memory:")
    cw.sync_to_memory(mem, user_id="ayush_01")

    facts = mem.get_what_i_know("ayush_01")
    assert any("Researching" in f.get("value", "") or "Coding & Tech" in f.get("value", "") for f in facts)
