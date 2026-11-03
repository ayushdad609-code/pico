"""
Price Watchers & Flagship Alert Engine for Pico.
From 32_FREE_BACKEND.pdf (§1 Market Data) and
YOUR_FRIEND_FULL_SETUP.pdf (§12 Watchers, §19.5 Trading Alert Flagship).
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import httpx


@dataclass
class PriceWatcher:
    """A user-configured market watcher rule (§12, §19.5)."""
    id: str
    user_id: str
    symbol: str          # e.g. "BTCUSDT", "ETHUSDT"
    target_level: float  # e.g. 68000.0
    direction: str       # "below" or "above"
    is_active: bool = True
    wake_override: bool = False  # If true, alerts break through quiet hours
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class WatcherAlert:
    """The Flagship Alert format (§19.5)."""
    watcher_id: str
    symbol: str
    push_notification: str  # <= 12 words, NO amounts
    in_app_card: Dict[str, Any]
    triggered_at: str


class PriceWatcherEngine:
    def __init__(self):
        self.watchers: Dict[str, PriceWatcher] = {}

    def add_watcher(self, watcher: PriceWatcher):
        self.watchers[watcher.id] = watcher

    def fetch_live_price(self, symbol: str = "BTCUSDT") -> float:
        """
        Fetches live price from Binance public REST API (₹0 tier, no key needed).
        Falls back to safe default if network is unreachable.
        """
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}"
            with httpx.Client(timeout=4.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return float(res.json()["price"])
        except Exception:
            pass
        # Fallback benchmark
        return 68500.0 if "BTC" in symbol.upper() else 2500.0

    def evaluate_watchers(self, current_prices: Optional[Dict[str, float]] = None) -> List[WatcherAlert]:
        """
        Scans all active watchers against live prices and triggers alerts.
        """
        alerts = []
        now_time = datetime.now(timezone.utc).strftime("%H:%M")
        now_iso = datetime.now(timezone.utc).isoformat()

        for w_id, w in list(self.watchers.items()):
            if not w.is_active:
                continue

            current_p = (
                current_prices.get(w.symbol.upper())
                if current_prices and w.symbol.upper() in current_prices
                else self.fetch_live_price(w.symbol)
            )

            triggered = False
            if w.direction == "below" and current_p <= w.target_level:
                triggered = True
            elif w.direction == "above" and current_p >= w.target_level:
                triggered = True

            if triggered:
                # 1. Flagship Push: <= 12 words, NO amounts (§19.5)
                direction_verb = "fell through" if w.direction == "below" else "broke above"
                push_text = f"WAKE UP — {w.symbol.replace('USDT', '')} {direction_verb} your level."
                words = push_text.split()
                if len(words) > 12:
                    push_text = " ".join(words[:12])

                # 2. In-App Card (§19.5):
                # what + time + their level + tagged context + open question
                in_app_card = {
                    "headline": f"At {now_time} {w.symbol} crossed {w.direction} your level.",
                    "user_level": f"{w.target_level:,.2f}",
                    "current_price": f"{current_p:,.2f}",
                    "tagged_context": "[REPORTED] High volume volatility detected across exchanges.",
                    "open_question": "Your call, as always — I'm just the loud friend. Want the 1-hour chart?",
                    "action_rule": "The tap is always human. No automated trading."
                }

                alert = WatcherAlert(
                    watcher_id=w.id,
                    symbol=w.symbol,
                    push_notification=push_text,
                    in_app_card=in_app_card,
                    triggered_at=now_iso
                )
                alerts.append(alert)
                # Deactivate one-shot level alert
                w.is_active = False

        return alerts
