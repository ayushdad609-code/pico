"""
Chrome Tabs Watcher & Browsing Context Engine for Pico.
Tracks active tabs, research topics, and domain categories via Chrome DevTools Protocol (CDP)
or direct extension/webhook events. Syncs browsing focus into Pico's memory.
"""

import time
import uuid
import logging
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import aiohttp

logger = logging.getLogger("pico.chrome_watcher")


CATEGORY_RULES = [
    ("Coding & Tech", [
        "github.com", "gitlab.com", "stackoverflow.com", "stackexchange.com",
        "docs.python.org", "pypi.org", "claude.ai", "chatgpt.com", "anthropic.com",
        "huggingface.co", "developer.mozilla.org", "w3schools.com", "colab.research.google.com"
    ]),
    ("Finance & Markets", [
        "tradingview.com", "zerodha.com", "kite.zerodha.com", "groww.in",
        "moneycontrol.com", "binance.com", "coinmarketcap.com", "coingecko.com",
        "nseindia.com", "bseindia.com", "screener.in"
    ]),
    ("Travel & Leisure", [
        "makemytrip.com", "booking.com", "airbnb.com", "agoda.com",
        "goibibo.com", "expedia.com", "tripadvisor.com", "irctc.co.in"
    ]),
    ("Shopping & Food", [
        "swiggy.com", "zomato.com", "amazon.in", "amazon.com", "flipkart.com",
        "myntra.com", "blinkit.com", "zepto.in"
    ]),
    ("Productivity", [
        "mail.google.com", "notion.so", "docs.google.com", "sheets.google.com",
        "calendar.google.com", "drive.google.com", "slack.com", "trello.com"
    ]),
    ("Social & Media", [
        "youtube.com", "twitter.com", "x.com", "reddit.com", "instagram.com",
        "linkedin.com", "facebook.com", "twitch.tv"
    ])
]


def categorize_url(url: str, title: str = "") -> str:
    """Categorizes a webpage based on URL domain or page title."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        
        for cat, domains in CATEGORY_RULES:
            if any(netloc == d or netloc.endswith("." + d) for d in domains):
                return cat
            if any(d.split(".")[0] in title.lower() for d in domains):
                return cat
    except Exception:
        pass

    # Fallback title heuristics
    title_lower = title.lower()
    if any(k in title_lower for k in ["code", "repo", "python", "git", "api"]):
        return "Coding & Tech"
    if any(k in title_lower for k in ["nifty", "stock", "chart", "crypto", "trading"]):
        return "Finance & Markets"
    if any(k in title_lower for k in ["hotel", "flight", "resort", "trip"]):
        return "Travel & Leisure"

    return "General Browsing"


@dataclass
class ChromeTab:
    tab_id: str
    url: str
    title: str
    domain: str
    category: str
    opened_at: float = field(default_factory=time.time)
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tab_id": self.tab_id,
            "url": self.url,
            "title": self.title,
            "domain": self.domain,
            "category": self.category,
            "opened_at": self.opened_at,
            "is_active": self.is_active
        }


class ChromeWatcher:
    """Tracks Chrome tabs and provides browsing focus analysis."""

    def __init__(self):
        self._tabs: Dict[str, ChromeTab] = {}

    def _extract_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            d = parsed.netloc.lower()
            return d[4:] if d.startswith("www.") else d
        except Exception:
            return "unknown"

    def record_tab(self, url: str, title: str = "", is_active: bool = True) -> ChromeTab:
        """Records a new or updated tab from extension, CDP, or webhook."""
        domain = self._extract_domain(url)
        category = categorize_url(url, title)
        tab_id = f"tab_{uuid.uuid4().hex[:6]}"

        tab = ChromeTab(
            tab_id=tab_id,
            url=url,
            title=title or domain,
            domain=domain,
            category=category,
            opened_at=time.time(),
            is_active=is_active
        )
        self._tabs[tab_id] = tab
        return tab

    def close_tab(self, tab_id: str) -> bool:
        if tab_id in self._tabs:
            del self._tabs[tab_id]
            return True
        return False

    def get_open_tabs(self) -> List[ChromeTab]:
        return list(self._tabs.values())

    def get_browsing_summary(self) -> Dict[str, Any]:
        """Summarizes currently open tabs, primary focus, and top domains."""
        tabs = self.get_open_tabs()
        if not tabs:
            return {
                "tab_count": 0,
                "primary_category": "Idle",
                "top_domains": [],
                "recent_tabs": []
            }

        # Count categories
        cat_counts: Dict[str, int] = {}
        domain_counts: Dict[str, int] = {}
        for t in tabs:
            cat_counts[t.category] = cat_counts.get(t.category, 0) + 1
            domain_counts[t.domain] = domain_counts.get(t.domain, 0) + 1

        primary_cat = max(cat_counts.items(), key=lambda x: x[1])[0]
        sorted_domains = sorted(domain_counts.keys(), key=lambda d: domain_counts[d], reverse=True)

        return {
            "tab_count": len(tabs),
            "primary_category": primary_cat,
            "category_distribution": cat_counts,
            "top_domains": sorted_domains[:5],
            "recent_tabs": [t.to_dict() for t in tabs[-5:]]
        }

    async def poll_cdp_tabs(self, cdp_url: str = "http://127.0.0.1:9222") -> List[ChromeTab]:
        """Polls Chrome DevTools Protocol /json/list endpoint to retrieve live tabs."""
        endpoint = f"{cdp_url}/json/list"
        new_tabs: List[ChromeTab] = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data:
                            if item.get("type") == "page":
                                url = item.get("url", "")
                                title = item.get("title", "")
                                if url and not url.startswith("chrome://"):
                                    tab = self.record_tab(url=url, title=title)
                                    new_tabs.append(tab)
        except Exception as e:
            logger.debug(f"CDP polling inactive/unavailable: {e}")

        return new_tabs

    def sync_to_memory(self, memory_store: Any, user_id: str = "ayush_01") -> None:
        """Records the user's active research focus into Pico's episodic memory."""
        summary = self.get_browsing_summary()
        if summary["tab_count"] == 0:
            return

        cat = summary["primary_category"]
        domains = ", ".join(summary["top_domains"][:3])
        fact_text = f"Researching: Active browsing focus on {cat} across {summary['tab_count']} tabs ({domains})."
        try:
            from pico.models import Fact, FactSource, FactStatus
            fact = Fact(
                key="active_browsing_research",
                value=fact_text,
                source=FactSource.OBSERVED,
                status=FactStatus.COMMITTED
            )
            memory_store.store_fact(user_id=user_id, fact=fact)
        except Exception as e:
            logger.warning(f"Memory sync failed: {e}")
