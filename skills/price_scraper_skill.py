"""
Live Web Item & Price Scraper Skill for Pico.
Scrapes live web pages or search snippets to extract product items,
currency symbols, live prices, and computes statistical analytics (min, max, average).
Equipped with SSRF protection and non-blocking timeouts.
"""

import re
import time
import httpx
from html.parser import HTMLParser
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional, Tuple

from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel


class WebPriceParser(HTMLParser):
    """Parses HTML DOM to detect product cards, titles, and price elements."""

    def __init__(self):
        super().__init__()
        self.items: List[Tuple[str, str]] = []
        self.current_title: Optional[str] = None
        self.current_price: Optional[str] = None
        self.in_title = False
        self.in_price = False

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        classes = attrs_d.get("class", "").lower()
        tag_lower = tag.lower()

        # Product title indicators
        if tag_lower in ["h2", "h3", "h4"] or "title" in classes or "product-name" in classes:
            self.in_title = True

        # Price indicators
        if "price" in classes or "amount" in classes or "cost" in classes:
            self.in_price = True

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in ["h2", "h3", "h4"]:
            self.in_title = False
        if self.in_price:
            self.in_price = False

    def handle_data(self, data):
        cleaned = data.strip()
        if not cleaned:
            return

        if self.in_title and not self.current_title:
            self.current_title = cleaned[:60]
        elif (self.in_price or re.search(r"[£$€₹]\s*[\d,]+(?:\.\d+)?", cleaned)) and not self.current_price:
            price_match = re.search(r"([£$€₹]|USD|INR|EUR|GBP)?\s*([\d,]+(?:\.\d+)?)", cleaned)
            if price_match:
                self.current_price = cleaned[:30]

        if self.current_title and self.current_price:
            self.items.append((self.current_title, self.current_price))
            self.current_title = None
            self.current_price = None


class ItemPriceScraperSkill(BaseSkill):
    name = "price_scraper"
    description = "Scrapes live web pages or queries to extract product items, currency, prices, and summary analytics (min, max, avg)."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "url": {"type": "string", "required": False, "description": "Target website URL to scrape items from"},
        "query": {"type": "string", "required": False, "description": "Search query for items if no URL is provided"}
    }

    DISALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254", "internal"]

    @classmethod
    def scrape_url(cls, url: str, timeout: float = 8.0) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Scrapes a URL and parses item prices."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)
        host = parsed.hostname.lower() if parsed.hostname else ""
        if any(dh in host for dh in cls.DISALLOWED_HOSTS) or host.startswith("192.168.") or host.startswith("10."):
            raise ValueError("Target host is blocked by security policy.")

        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; Mobile; Pico/1.0)"
        }
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP error {resp.status_code} fetching page.")

        parser = WebPriceParser()
        parser.feed(resp.text)

        items = []
        numeric_prices = []
        primary_currency = "£"

        for title, price_str in parser.items:
            # Extract currency and numeric value
            curr_match = re.search(r"([£$€₹]|USD|INR|EUR|GBP)", price_str)
            curr = curr_match.group(1) if curr_match else "£"
            primary_currency = curr

            num_str = re.sub(r"[^\d\.]", "", price_str)
            if num_str:
                try:
                    val = float(num_str)
                    numeric_prices.append(val)
                    items.append({
                        "name": title,
                        "price_str": price_str,
                        "price": val,
                        "currency": curr
                    })
                except ValueError:
                    pass

        analytics = {}
        if numeric_prices:
            analytics = {
                "count": len(numeric_prices),
                "min": min(numeric_prices),
                "max": max(numeric_prices),
                "avg": round(sum(numeric_prices) / len(numeric_prices), 2),
                "currency": primary_currency
            }

        return items, analytics

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        url = inputs.get("url", "").strip()
        query = inputs.get("query", "").strip()

        # Default fallback target if neither is provided: Books sandbox
        if not url and not query:
            url = "https://books.toscrape.com/"

        try:
            if url:
                items, analytics = self.scrape_url(url)
                source_label = url
            else:
                from .browser_skill import BrowserSkill
                snippets = BrowserSkill.search_web(f"{query} price", max_results=5)
                items = []
                numeric_prices = []
                for s in snippets:
                    p_match = re.search(r"([£$€₹]|Rs\.?)\s*([\d,]+(?:\.\d+)?)", s)
                    if p_match:
                        curr = p_match.group(1)
                        val = float(p_match.group(2).replace(",", ""))
                        numeric_prices.append(val)
                        items.append({"name": s[:60], "price_str": f"{curr}{val}", "price": val, "currency": curr})

                analytics = {
                    "count": len(numeric_prices),
                    "min": min(numeric_prices) if numeric_prices else 0.0,
                    "max": max(numeric_prices) if numeric_prices else 0.0,
                    "avg": round(sum(numeric_prices) / len(numeric_prices), 2) if numeric_prices else 0.0,
                    "currency": items[0]["currency"] if items else "₹"
                }
                source_label = f"Web Search ('{query}')"

            curr_sym = analytics.get("currency", "£")
            summary_lines = [
                f"🛍️ **Live Web Item Price Scraper** ({source_label}):\n",
                f"• **Items Found:** {len(items)} items",
            ]
            if analytics:
                summary_lines.append(
                    f"• **Price Range:** {curr_sym}{analytics['min']:.2f} — {curr_sym}{analytics['max']:.2f}"
                )
                summary_lines.append(
                    f"• **Average Price:** {curr_sym}{analytics['avg']:.2f}"
                )

            summary_lines.append("\n**Sample Scraped Items:**")
            for itm in items[:6]:
                summary_lines.append(f"• `{itm['name'][:40]}`: **{itm['price_str']}**")

            return SkillResult(
                success=True,
                skill_name=self.name,
                output={
                    "source": source_label,
                    "items": items,
                    "analytics": analytics,
                    "summary_text": "\n".join(summary_lines)
                },
                execution_time_ms=round((time.time() - start_t) * 1000, 2)
            )

        except Exception as e:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error=f"Web price scraping error: {str(e)}",
                execution_time_ms=round((time.time() - start_t) * 1000, 2)
            )
