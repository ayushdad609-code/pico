"""
Telegram Mobile Bot Bridge for Pico ("Your Friend").
From YOUR_FRIEND_FULL_SETUP.pdf (§8 App Structure, §10 Pipeline, §12 Hands/Connectors).

Connects Pico directly to your phone via Telegram Bot API using async long-polling:
- Real-time conversation running through the 7-step pipeline & emotion examiner
- Routine spine delivery (Morning Brief at 07:30, Evening Review at 21:30)
- Interactive inline keyboards for costume change and approval cards ([Approve] / [Reject])
- Real-time Binance crypto price watcher alerts pushed directly to your chat
- All skills accessible directly from mobile chat (/sip, /food, /browse, /pomo, /lockin, etc.)
- Quiet hours strictly respected (22:00 - 07:00).
"""

import os
import sys
import time
import json
import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone

import aiohttp

from pico.models import UserProfile, PicoEmotion
from pico.onboarding import OnboardingFlow
from pico.memory import MemoryStore
from pico.pipeline import PipelineEngine
from pico.routine import RoutineGraph
from pico.briefs import BriefGenerator
from pico.artifacts import ArtifactFactory
from pico.tokens import TokenManager
from pico.skills import SkillRegistry
from pico.watchers import PriceWatcherEngine, PriceWatcher
from pico.browser_handoff import BrowserHandoffEngine


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pico_telegram")


class TelegramApiClient:
    """Async wrapper for the official Telegram Bot HTTP API."""

    def __init__(self, bot_token: str, session: Optional[aiohttp.ClientSession] = None):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.session = session

    async def _request(self, method: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 35.0) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/{method}"
        try:
            if not self.session:
                async with aiohttp.ClientSession() as temp_session:
                    async with temp_session.post(url, json=payload or {}, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data if data.get("ok") else None
                        else:
                            text = await resp.text()
                            logger.error(f"Telegram API {method} HTTP {resp.status}: {text}")
                            return None
            else:
                async with self.session.post(url, json=payload or {}, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data if data.get("ok") else None
                    else:
                        text = await resp.text()
                        logger.error(f"Telegram API {method} HTTP {resp.status}: {text}")
                        return None
        except Exception as e:
            logger.error(f"Telegram API request failed: {e}")
            return None

    async def get_me(self) -> Optional[Dict[str, Any]]:
        res = await self._request("getMe")
        return res.get("result") if res else None

    async def get_updates(self, offset: Optional[int] = None, timeout: int = 25) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        res = await self._request("getUpdates", payload, timeout=timeout + 5)
        return res.get("result", []) if res else []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup

        res = await self._request("sendMessage", payload)
        if not res and parse_mode:
            # Fallback without markdown if markdown parsing failed
            payload.pop("parse_mode", None)
            res = await self._request("sendMessage", payload)
        return res.get("result") if res else None

    async def send_photo(
        self,
        chat_id: int,
        photo_bytes: bytes,
        caption: Optional[str] = None,
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/sendPhoto"
        data = aiohttp.FormData()
        data.add_field("chat_id", str(chat_id))
        data.add_field("photo", photo_bytes, filename="screen.jpg", content_type="image/jpeg")
        if caption:
            data.add_field("caption", caption)
        if reply_markup:
            data.add_field("reply_markup", json.dumps(reply_markup))

        try:
            if not self.session:
                async with aiohttp.ClientSession() as s:
                    async with s.post(url, data=data, timeout=aiohttp.ClientTimeout(total=20.0)) as resp:
                        if resp.status == 200:
                            res = await resp.json()
                            return res.get("result")
                        else:
                            txt = await resp.text()
                            logger.error(f"Telegram API sendPhoto error {resp.status}: {txt}")
                            return None
            else:
                async with self.session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=20.0)) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        return res.get("result")
                    else:
                        txt = await resp.text()
                        logger.error(f"Telegram API sendPhoto error {resp.status}: {txt}")
                        return None
        except Exception as e:
            logger.error(f"sendPhoto failed: {e}")
            return None

    async def send_chat_action(self, chat_id: int, action: str = "typing"):
        await self._request("sendChatAction", {"chat_id": chat_id, "action": action})

    async def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None):
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        await self._request("answerCallbackQuery", payload)


class PicoTelegramBot:
    """The complete Telegram Bot backend for Pico."""

    def __init__(
        self,
        bot_token: str,
        db_path: str = "pico_chat.db",
        allowed_user_id: Optional[int] = None
    ):
        self.bot_token = bot_token
        self.allowed_user_id = allowed_user_id
        self.api = TelegramApiClient(bot_token)
        self.memory = MemoryStore(db_path=db_path)
        self.pipeline = PipelineEngine(self.memory)
        self.token_mgr = TokenManager()
        self.skill_registry = SkillRegistry()
        self.watcher_mgr = PriceWatcherEngine()
        self.handoff = BrowserHandoffEngine(cdp_port=9222, web_port=8765)
        self.handoff.on_handoff_complete_callback = self._on_browser_handoff_complete
        self.active_handoff_chat_id: Optional[int] = None
        self.user_modes: Dict[int, str] = {}
        self.user_profiles: Dict[int, UserProfile] = {}
        self.last_morning_brief_date: Optional[str] = None
        self.last_evening_review_date: Optional[str] = None
        self.is_running = False

    def get_or_create_profile(self, chat_id: int, first_name: str) -> UserProfile:
        """Retrieves or provisions UserProfile for this Telegram chat."""
        if chat_id not in self.user_profiles:
            profile = OnboardingFlow.create_fast_path_profile(
                user_id=f"tg_{chat_id}",
                name=first_name,
                nickname=first_name,
                goal_90d="Stay disciplined, healthy, and on track with daily habits."
            )
            self.user_profiles[chat_id] = profile
        return self.user_profiles[chat_id]

    async def _on_browser_handoff_complete(self, session_data: Dict[str, Any]):
        """Pushes a notification to Telegram when handoff completes via the web viewer."""
        if self.active_handoff_chat_id:
            domain = session_data.get("domain", "website")
            count = session_data.get("cookie_count", 0)
            msg = (
                f"🎉 **Session Locked In!**\n\n"
                f"Pico captured **{count} session cookies** for `{domain}`!\n"
                f"I am now logged in as you and ready to run your tasks on this site. 🌐✨"
            )
            await self.api.send_message(self.active_handoff_chat_id, msg)

    def build_main_keyboard(self) -> Dict[str, Any]:
        """Persistent quick-reply keyboard."""
        return {
            "keyboard": [
                [{"text": "🗺️ Day Path"}, {"text": "☀️ Morning Brief"}, {"text": "🌙 Evening Review"}],
                [{"text": "📖 What You Know"}, {"text": "👕 Change Outfit"}, {"text": "🪙 Token Status"}],
                [{"text": "⚡ Skills Menu"}, {"text": "🔒 Lock In Mode"}]
            ],
            "resize_keyboard": True,
            "persistent": True
        }

    def build_outfit_inline_keyboard(self) -> Dict[str, Any]:
        """Inline buttons for costume selection."""
        return {
            "inline_keyboard": [
                [
                    {"text": "👕 Chill", "callback_data": "outfit_chill"},
                    {"text": "🏋️ Gym", "callback_data": "outfit_gym"},
                    {"text": "📈 Trading", "callback_data": "outfit_trading"}
                ],
                [
                    {"text": "💻 Coding", "callback_data": "outfit_coding"},
                    {"text": "🍳 Cooking", "callback_data": "outfit_cooking"},
                    {"text": "🚀 Startups", "callback_data": "outfit_startups"}
                ],
                [
                    {"text": "📚 Study", "callback_data": "outfit_study"},
                    {"text": "✈️ Travel", "callback_data": "outfit_travel"},
                    {"text": "🔒 Lock In", "callback_data": "outfit_lock_in"}
                ]
            ]
        }

    def build_approval_keyboard(self, action_id: str) -> Dict[str, Any]:
        """Inline buttons for approval cards (§12 Permission Ladder)."""
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": f"approve_{action_id}"},
                    {"text": "❌ Reject", "callback_data": f"reject_{action_id}"}
                ]
            ]
        }

    async def handle_message(self, chat_id: int, text: str, user_first_name: str):
        """Processes an incoming message from the user."""
        profile = self.get_or_create_profile(chat_id, user_first_name)
        current_mode = self.user_modes.get(chat_id, "chill")
        text_clean = text.strip()

        # Send typing action
        await self.api.send_chat_action(chat_id, "typing")

        # 1. /start or Help
        if text_clean in ["/start", "start", "/help", "help"]:
            welcome_text = (
                f"🌟 **Hey {profile.nickname or profile.name}! I'm Pico!** ✨\n\n"
                "I'm your daily companion, routine keeper, and habit friend! "
                "I've got my notebook open, my stickers aligned, and I'm ready to keep our days on track.\n\n"
                "💡 **Quick shortcuts:**\n"
                "• 🗺️ Tap **Day Path** to see today's routine spine\n"
                "• ☀️ Tap **Morning Brief** / 🌙 **Evening Review**\n"
                "• 👕 Tap **Change Outfit** to switch modes (Gym, Trading, Coding, etc.)\n"
                "• Or just talk to me like a friend — I'm right here!"
            )
            await self.api.send_message(
                chat_id,
                welcome_text,
                reply_markup=self.build_main_keyboard()
            )
            return

        # 2. Routine Day Path
        if text_clean in ["/path", "🗺️ Day Path"]:
            routine_graph = RoutineGraph.seed_from_profile(profile)
            path = routine_graph.render_day_path()
            lines = ["🗺️ **Today's Day Path (Routine Spine)**:\n"]
            for p in path:
                indicator = "📍 [NOW]" if p["is_active"] else "  •"
                status_emoji = "✅" if p["status"] == "completed" else "⏳"
                lines.append(f"{indicator} **{p['time']}** — {p['name']} ({p['mode']}) {status_emoji}")
            lines.append("\n*Quiet hours strictly protected between 22:00 and 07:00.*")
            await self.api.send_message(chat_id, "\n".join(lines))
            return

        # 3. Morning Brief
        if text_clean in ["/brief", "☀️ Morning Brief"]:
            routine_graph = RoutineGraph.seed_from_profile(profile)
            brief = BriefGenerator.generate_morning_brief(profile, routine_graph)
            await self.api.send_message(chat_id, f"☀️ **Morning Brief**\n\n{brief}")
            return

        # 4. Evening Review
        if text_clean in ["/review", "🌙 Evening Review"]:
            review = BriefGenerator.generate_evening_review(
                profile=profile,
                streak_count=1,
                completed_tasks=["Active check-in completed!"]
            )
            await self.api.send_message(chat_id, f"🌙 **Evening Review (21:30)**\n\n{review}")
            return

        # 5. What Pico Knows About You
        if text_clean in ["/whatiknow", "/what-i-know", "📖 What You Know"]:
            facts = self.memory.get_what_i_know(profile.user_id)
            if not facts:
                msg = "📖 **What Pico Knows About You**:\n\n*Notebook is still fresh! Share your habits, favorite food, or workout PRs and I'll keep them safe.*"
            else:
                lines = [f"📖 **What Pico Knows About You ({len(facts)} facts)**:\n"]
                for f in facts:
                    lines.append(f"• **{f['key']}**: {f['value']} *(status: {f['status']})*")
                lines.append("\n💡 *Privacy Rule: This memory stays 100% private and is never sent to free Gemini.*")
                msg = "\n".join(lines)
            await self.api.send_message(chat_id, msg)
            return

        # 6. Change Outfit / Mode Selector
        if text_clean in ["/outfit", "/mode", "👕 Change Outfit"]:
            await self.api.send_message(
                chat_id,
                f"👕 **Current Outfit:** [{current_mode.upper()}]\n\nPick a mode to change my outfit and active focus:",
                reply_markup=self.build_outfit_inline_keyboard()
            )
            return

        # 7. Lock In Mode 🔒
        if text_clean in ["/lockin", "🔒 Lock In Mode"]:
            token_acc = self.token_mgr.get_or_create_account(profile.user_id)
            success, lock_msg = self.token_mgr.enter_lock_in_mode(token_acc)
            if success:
                self.user_modes[chat_id] = "lock_in"
                await self.api.send_message(
                    chat_id,
                    f"🎧 **LOCKED IN 🔒**\n\n{lock_msg}\n\n*Zero small talk. Focused execution mode engaged.*"
                )
            else:
                await self.api.send_message(chat_id, f"⚠️ {lock_msg}")
            return

        # 8. Token Meter Status
        if text_clean in ["/tokens", "🪙 Token Status"]:
            token_acc = self.token_mgr.get_or_create_account(profile.user_id)
            pct = token_acc.usage_percentage
            msg = (
                f"🪙 **Tokens Status (You Tab)**:\n\n"
                f"• Remaining: **{token_acc.tokens_remaining:,}** / {token_acc.monthly_allowance:,} tokens\n"
                f"• Usage: **{pct:.1f}%**\n"
                f"• Mode: {'⚠️ LOW POWER FRIEND (Basic chat & watchers alive)' if token_acc.is_low_power else '⚡ Full Power'}\n"
                f"• Lock In Trials: **{token_acc.lock_in_sessions_left}** sessions left this month\n\n"
                f"*40M free monthly tokens provided automatically!*"
            )
            await self.api.send_message(chat_id, msg)
            return

        # 9. Skills Menu
        if text_clean in ["/skills", "⚡ Skills Menu"]:
            msg = (
                "⚡ **Pico Built-in Skills Catalog**:\n\n"
                "• 🥗 `/macros [weight] [height]` — TDEE & Indian macro splits\n"
                "• 🍲 `/food <dish> [qty]` — Indian nutrition lookup (e.g. `/food roti 2`)\n"
                "• ⏱️ `/pomo <hours>` — Pomodoro deep work plan (e.g. `/pomo 2.5`)\n"
                "• 📈 `/levels <H> <L> <C>` — Fibonacci & pivot levels\n"
                "• 🚀 `/runway <cash> <burn>` — Startup runway calculator\n"
                "• ✈️ `/pack <city> [days]` — Smart packing checklist\n"
                "• 🌐 `/browse <url>` — Cloud browser clean fetcher\n"
                "• 🎮 `/login <url>` — Interactive browser login takeover (like Muse)\n"
                "• 🔐 `/sessions` — View active authenticated sessions\n"
                "• 📝 `/script <text>` — Script Doctor hook rater\n"
                "• 💰 `/sip <amt> <rate> <years>` — SIP Compounding Calculator\n\n"
                "*Tap any command above or just ask me naturally!*"
            )
            await self.api.send_message(chat_id, msg)
            return

        # 10. SIP Calculator Artifact
        if text_clean.startswith("/sip"):
            parts = text_clean.split()
            monthly = float(parts[1]) if len(parts) > 1 else 5000.0
            rate = float(parts[2]) if len(parts) > 2 else 15.0
            years = int(parts[3]) if len(parts) > 3 else 20
            artifact = ArtifactFactory.create_sip_calculator(
                user_id=profile.user_id,
                monthly_investment=monthly,
                expected_cagr=rate,
                tenure_years=years
            )
            msg = (
                f"💰 **Living SIP Compounding Calculator**:\n\n"
                f"• Monthly SIP: **₹{monthly:,.0f}**\n"
                f"• Expected Return: **{rate}% p.a.**\n"
                f"• Horizon: **{years} Years**\n\n"
                f"📊 **Total Invested:** {artifact.summary_header['metric_secondary']}\n"
                f"🏆 **Expected Wealth:** {artifact.summary_header['metric_primary']}\n\n"
                f"💬 *\"{artifact.his_line}\"*"
            )
            await self.api.send_message(chat_id, msg)
            return

        # 11. Food Lookup Skill
        if text_clean.startswith("/food"):
            parts = text_clean.split()
            dish = parts[1] if len(parts) > 1 else "roti"
            qty = float(parts[2]) if len(parts) > 2 else 1.0
            res = self.skill_registry.execute_skill("food_lookup", {"food_item": dish, "quantity": qty})
            if res.success:
                out = res.output
                m = out["macronutrients"]
                msg = (
                    f"🍲 **Nutrition for {out['item_name']} ({out['servings']}x)**:\n\n"
                    f"• Calories: **{out['calories_kcal']} kcal**\n"
                    f"• Protein: **{m['protein_g']}g** | Carbs: **{m['carbs_g']}g** | Fat: **{m['fat_g']}g**\n\n"
                    f"💬 *\"{out['his_line']}\"*"
                )
            else:
                msg = f"⚠️ {res.error}"
            await self.api.send_message(chat_id, msg)
            return

        # 12. Pomodoro Deep Work Planner
        if text_clean.startswith("/pomo"):
            parts = text_clean.split()
            hrs = float(parts[1]) if len(parts) > 1 else 2.0
            res = self.skill_registry.execute_skill("pomodoro_planner", {"available_hours": hrs})
            if res.success:
                out = res.output
                timeline_preview = "\n".join([f"  • {item}" for item in out["timeline"][:4]])
                msg = (
                    f"⏱️ **Pomodoro Flow Plan ({hrs}h window)**:\n\n"
                    f"• Focus time: **{out['total_focus_time_mins']} mins** across {out['focus_cycles']} cycles\n"
                    f"• Schedule:\n{timeline_preview}\n\n"
                    f"💬 *\"{out['his_line']}\"*"
                )
            else:
                msg = f"⚠️ {res.error}"
            await self.api.send_message(chat_id, msg)
            return

        # 13a. Interactive Browser Login Takeover (Like Muse)
        if text_clean in ["/gmail", "/login gmail"]:
            target_url = "https://accounts.google.com"
        elif text_clean.startswith("/login"):
            parts = text_clean.split(maxsplit=1)
            if len(parts) < 2:
                await self.api.send_message(
                    chat_id,
                    "Usage: `/login <url>` (e.g. `/login gmail`, `/login https://github.com/login`, or `/login https://x.com`)\n\n"
                    "I'll visit the site, pause at the login screen, and hand you the wheel so you can fill your values!"
                )
                return

            target_url = parts[1].strip()
            if target_url.lower() in ["gmail", "google"]:
                target_url = "https://accounts.google.com"
            elif not target_url.startswith("http"):
                target_url = "https://" + target_url

            self.active_handoff_chat_id = chat_id
            await self.api.send_chat_action(chat_id, "typing")
            await self.api.send_message(chat_id, f"🚀 Launching Cloud Chromium & navigating to `{target_url}`...")

            takeover_res = await self.handoff.start_takeover(target_url)
            domain = takeover_res["domain"]
            takeover_url = takeover_res["takeover_url"]
            ss_bytes = takeover_res.get("screenshot_bytes")

            caption = (
                f"🎮 **Browser Takeover Handoff**\n\n"
                f"I've opened **{domain}** in our sandboxed browser!\n\n"
                f"👉 **Open this link on your phone to take control:**\n"
                f"{takeover_url}\n\n"
                f"1. Tap input fields on the screen to focus.\n"
                f"2. Type your credentials with the keyboard bar.\n"
                f"3. When you're in, tap **[✅ Done, Pico Take Over!]** below!"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📸 Refresh Screenshot", "callback_data": "takeover_refresh"}],
                    [{"text": "✅ Done, Pico Take Over!", "callback_data": "takeover_done"}],
                    [{"text": "❌ Cancel Handoff", "callback_data": "takeover_cancel"}]
                ]
            }

            sent = None
            if ss_bytes:
                sent = await self.api.send_photo(chat_id, ss_bytes, caption=caption, reply_markup=keyboard)
            if not sent:
                await self.api.send_message(chat_id, caption, reply_markup=keyboard)
            return

        # 13b. Check Saved Login Sessions
        if text_clean.startswith("/sessions"):
            sessions = self.handoff.vault.list_sessions()
            if not sessions:
                await self.api.send_message(
                    chat_id,
                    "🔐 **Saved Browser Sessions:** (Empty)\n\n"
                    "You haven't logged into any sites with Pico yet!\n"
                    "Try: `/login https://github.com/login` to log into your first site."
                )
                return

            lines = ["🔐 **Active Authenticated Sessions:**\n"]
            for dom, info in sessions.items():
                lines.append(f"• **{dom}**: {info['cookie_count']} cookies (saved {info['saved_at'][:10]})")
            lines.append("\nWhen you ask me to browse or track these sites, I automatically use these saved cookies!")
            await self.api.send_message(chat_id, "\n".join(lines))
            return

        # 13c. Browser Agent
        if text_clean.startswith("/browse"):
            parts = text_clean.split(maxsplit=1)
            if len(parts) < 2:
                await self.api.send_message(chat_id, "Usage: `/browse <url>` (e.g. `/browse https://example.com`)")
                return
            url = parts[1].strip()
            res = self.skill_registry.execute_skill("browser_agent", {"url": url})
            if res.success:
                out = res.output
                lines = [l.strip() for l in out["text_content"].splitlines() if l.strip()][:6]
                preview = "\n".join(lines)
                msg = (
                    f"🌐 **Browser Agent: {out.get('title') or out['host']}**\n\n"
                    f"• URL: {out['url']} (Status: {out['status_code']})\n"
                    f"• Word count: {out['word_count']} words\n\n"
                    f"**Extracted Content:**\n{preview}\n\n"
                    f"💬 *\"{out['his_line']}\"*"
                )
            else:
                msg = f"⚠️ Browser error: {res.error}"
            await self.api.send_message(chat_id, msg)
            return

        # 14. Real-time Crypto Watcher
        if text_clean.startswith("/watch"):
            parts = text_clean.split()
            if len(parts) >= 2:
                try:
                    level = float(parts[1])
                    w = PriceWatcher(
                        id=f"watch_btc_{chat_id}_{int(level)}",
                        user_id=profile.user_id,
                        symbol="BTCUSDT",
                        target_level=level,
                        direction="above" if level > 60000 else "below"
                    )
                    self.watcher_mgr.add_watcher(w)
                    await self.api.send_message(
                        chat_id,
                        f"🎯 **Watcher Armed:** Watching BTC at **${level:,.0f}**!\n"
                        f"The second price touches this level, I'll send an instant alert!"
                    )
                    return
                except ValueError:
                    pass

        # 15. Default: Run Full 7-Step Pipeline
        res = self.pipeline.run(
            user_message=text_clean,
            profile=profile,
            active_mode=current_mode
        )

        # Deduct usage tokens (~150 tokens)
        self.token_mgr.record_usage(profile.user_id, 150)

        # Format character response
        mode_tag = res.get("mode", current_mode).upper()
        emotion = res.get("emotion", "calm")
        output_text = res.get("output", "")

        reply = f"🌟 **[Pico | Mode: {mode_tag} | Emotion: {emotion}]**\n\n{output_text}"

        # If facts were extracted, add pencil-note animation
        if res.get("facts_saved"):
            saved_str = ", ".join(res["facts_saved"])
            reply += f"\n\n✏️ *Pencil-note: Pico remembered: {saved_str}*"

        await self.api.send_message(chat_id, reply)

    async def handle_callback_query(self, callback_query: Dict[str, Any]):
        """Handles button clicks from inline keyboards."""
        cb_id = callback_query.get("id")
        data = callback_query.get("data", "")
        message = callback_query.get("message", {})
        chat_id = message.get("chat", {}).get("id")

        if not chat_id:
            await self.api.answer_callback_query(cb_id)
            return

        # Outfit change callback
        if data.startswith("outfit_"):
            new_outfit = data.replace("outfit_", "")
            self.user_modes[chat_id] = new_outfit
            await self.api.answer_callback_query(cb_id, text=f"Switched to {new_outfit.upper()} outfit! ✨")
            await self.api.send_message(
                chat_id,
                f"👕 *Costume-change animation (1s)*: Pico changed into **[{new_outfit.upper()}]** mode!"
            )
            return

        # Approval Card callbacks
        if data.startswith("approve_"):
            action_id = data.replace("approve_", "")
            await self.api.answer_callback_query(cb_id, text="Action approved! ✅")
            await self.api.send_message(
                chat_id,
                f"✅ **Approved!** Action '{action_id}' confirmed and locked in."
            )
            return

        if data.startswith("reject_"):
            action_id = data.replace("reject_", "")
            await self.api.answer_callback_query(cb_id, text="Action rejected ❌")
            await self.api.send_message(
                chat_id,
                f"❌ **Cancelled.** Action '{action_id}' was dropped. Staying safe!"
            )
            return

        # Browser Takeover Callbacks
        if data == "takeover_done":
            self.active_handoff_chat_id = chat_id
            await self.api.answer_callback_query(cb_id, text="Locking in cookies... 🍪")
            fin = await self.handoff.finalize_session()
            await self.api.send_message(
                chat_id,
                f"🎉 **Handoff Complete!**\n\n"
                f"Pico successfully locked in **{fin['cookie_count']} session cookies** for `{fin['domain']}`! 🍪✨\n"
                f"Now whenever you ask me to browse or check this site, I will access it logged in as you!"
            )
            return

        if data == "takeover_refresh":
            await self.api.answer_callback_query(cb_id, text="Snapping fresh screen... 📸")
            ss = await self.handoff.capture_current_screenshot()
            if ss:
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "🌐 Open Interactive Screen", "url": f"http://localhost:{self.handoff.web_port}/takeover"}],
                        [{"text": "📸 Refresh Screenshot", "callback_data": "takeover_refresh"}],
                        [{"text": "✅ Done, Pico Take Over!", "callback_data": "takeover_done"}],
                        [{"text": "❌ Cancel Handoff", "callback_data": "takeover_cancel"}]
                    ]
                }
                await self.api.send_photo(chat_id, ss, caption="📸 **Current Live Browser Screen**:", reply_markup=keyboard)
            else:
                await self.api.send_message(chat_id, "⚠️ Could not capture live screen.")
            return

        if data == "takeover_cancel":
            await self.api.answer_callback_query(cb_id, text="Handoff cancelled")
            await self.api.send_message(chat_id, "🛑 Browser takeover cancelled.")
            return

        await self.api.answer_callback_query(cb_id)

    async def scheduled_heartbeat_loop(self, chat_id: int):
        """Background loop for scheduled briefs and watcher push alerts."""
        while self.is_running:
            try:
                now_utc = datetime.now(timezone.utc)
                hour = now_utc.hour
                minute = now_utc.minute
                today_str = now_utc.strftime("%Y-%m-%d")

                # Respect Quiet Hours (22:00 - 07:00 UTC/local)
                is_quiet_hours = (hour >= 22 or hour < 7)

                if not is_quiet_hours:
                    # 1. Morning Brief at 07:30
                    if hour == 7 and minute == 30 and self.last_morning_brief_date != today_str:
                        self.last_morning_brief_date = today_str
                        profile = self.get_or_create_profile(chat_id, "Friend")
                        routine_graph = RoutineGraph.seed_from_profile(profile)
                        brief = BriefGenerator.generate_morning_brief(profile, routine_graph)
                        await self.api.send_message(
                            chat_id,
                            f"☀️ **Good Morning! Here is your Morning Brief:**\n\n{brief}"
                        )

                    # 2. Evening Review at 21:30
                    if hour == 21 and minute == 30 and self.last_evening_review_date != today_str:
                        self.last_evening_review_date = today_str
                        profile = self.get_or_create_profile(chat_id, "Friend")
                        review = BriefGenerator.generate_evening_review(
                            profile=profile,
                            streak_count=1,
                            completed_tasks=["Active today!"]
                        )
                        await self.api.send_message(
                            chat_id,
                            f"🌙 **Evening Review (21:30):**\n\n{review}"
                        )

                    # 3. Check live price watchers
                    alerts = self.watcher_mgr.evaluate_watchers()
                    for alert in alerts:
                        await self.api.send_message(
                            chat_id,
                            f"🚨 **Pico Watcher Alert!**\n\n{alert.push_notification}"
                        )

            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")

            # Sleep 60s between checks
            await asyncio.sleep(60)

    async def start_polling(self):
        """Main long-polling event loop."""
        self.is_running = True
        logger.info("Connecting to Telegram Bot API...")
        me = await self.api.get_me()
        if not me:
            logger.error("❌ Failed to verify Telegram Bot token. Please check your TELEGRAM_BOT_TOKEN.")
            return

        bot_name = me.get("first_name", "Pico")
        bot_user = me.get("username", "pico_bot")
        print("\n" + "=" * 65)
        print(f"🌟 PICO TELEGRAM BOT IS LIVE AND RUNNING!")
        print(f"   Bot Name:     {bot_name}")
        print(f"   Bot Username: @{bot_user}")
        print(f"   Open Telegram and search for: @{bot_user}")
        print("=" * 65 + "\n")

        offset = None
        background_task = None

        try:
            while self.is_running:
                updates = await self.api.get_updates(offset=offset, timeout=20)
                for u in updates:
                    offset = u["update_id"] + 1

                    # Handle Message
                    if "message" in u:
                        msg = u["message"]
                        chat_id = msg.get("chat", {}).get("id")
                        user_info = msg.get("from", {})
                        first_name = user_info.get("first_name", "Friend")
                        text = msg.get("text", "")

                        if chat_id and text:
                            # Start scheduled background loop on first message from user
                            if background_task is None:
                                background_task = asyncio.create_task(self.scheduled_heartbeat_loop(chat_id))

                            logger.info(f"[{first_name} | {chat_id}]: {text}")
                            await self.handle_message(chat_id, text, first_name)

                    # Handle Callback Query
                    elif "callback_query" in u:
                        await self.handle_callback_query(u["callback_query"])

                if not updates:
                    await asyncio.sleep(0.5)
                else:
                    await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        finally:
            if background_task:
                background_task.cancel()
            self.is_running = False
            logger.info("Telegram Bot stopped.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        env_paths = [".env", "pico/.env", "/data/data/com.termux/files/home/pico/.env"]
        for ep in env_paths:
            if os.path.exists(ep):
                try:
                    with open(ep) as f:
                        for line in f:
                            if line.startswith("TELEGRAM_BOT_TOKEN="):
                                token = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                                break
                    if token:
                        break
                except Exception:
                    pass

    if not token and len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        token = sys.argv[1]

    if not token:
        print("\n" + "=" * 65)
        print("🤖 PICO TELEGRAM BOT CONFIGURATION")
        print("=" * 65)
        print("No TELEGRAM_BOT_TOKEN found in environment!")
        print("\nTo connect Pico to Telegram:")
        print("1. Open Telegram on your phone and search for: @BotFather")
        print("2. Send: /newbot")
        print("3. Follow prompts to name it (e.g. 'Pico My Friend') and choose a username (e.g. 'pico_friend_bot')")
        print("4. Copy the API token BotFather gives you.\n")
        print("Then run Pico Telegram Bot:")
        print("  export TELEGRAM_BOT_TOKEN='your-bot-token'")
        print("  python3 -m pico.telegram_bot")
        print("Or directly:")
        print("  python3 -m pico.telegram_bot <your-bot-token>\n")
        print("=" * 65 + "\n")
        sys.exit(1)

    bot = PicoTelegramBot(bot_token=token)
    try:
        asyncio.run(bot.start_polling())
    except KeyboardInterrupt:
        print("\nPico Telegram Bot stopped cleanly. 👋")


if __name__ == "__main__":
    main()
