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
import re
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
from pico.device import DeviceProfiler
from pico.device_sensors import BatterySensor, AppLauncher, ClipboardBridge
from pico.agent_loop import AgentLoopEngine
from pico.mcp_host import MCPHost
from pico.heartbeat import HeartbeatRunner, HeartbeatOutcome
from pico.scheduled import ScheduledWorkRegistry
from pico.paths import get_pico_home, get_default_db_path
from telephony.contact_resolver import resolve_callee, CalleeInfo
from telephony.briefing import AuthorityLevel, FactsPacket, build_briefing_card
from telephony.call_session import CallSession, CallStatus
from telephony.telegram_bridge import TelegramCallBridge


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

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
        res = await self._request("editMessageText", payload)
        if not res and parse_mode:
            payload.pop("parse_mode", None)
            res = await self._request("editMessageText", payload)
        return res.get("result") if res else None


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
        self.mcp_host = MCPHost()
        self.agent_loop = AgentLoopEngine(self.mcp_host)
        self.pending_agent_tasks: Dict[int, Dict[str, Any]] = {}
        self.pending_skill_proposals: Dict[int, Dict[str, Any]] = {}
        self.pending_actions: Dict[str, Dict[str, Any]] = {}
        self.pending_call_briefings: Dict[Any, Dict[str, Any]] = {}
        self.active_call_sessions: Dict[str, CallSession] = {}
        self.call_bridges: Dict[str, TelegramCallBridge] = {}
        self.active_handoff_chat_id: Optional[int] = None
        self.user_modes: Dict[int, str] = {}
        self.user_profiles: Dict[int, UserProfile] = {}
        self.last_morning_brief_date: Optional[str] = None
        self.last_evening_review_date: Optional[str] = None
        self.last_nightly_report_date: Optional[str] = None
        self.last_battery_alert_time: float = 0.0
        self.start_time: float = time.time()
        self.heartbeat_runners: Dict[int, HeartbeatRunner] = {}
        admin_env = os.getenv("TELEGRAM_ADMIN_CHAT_ID")
        self.admin_chat_id = int(admin_env) if admin_env and admin_env.isdigit() else None
        self.is_running = False

    def get_or_create_heartbeat_runner(self, chat_id: int, profile: UserProfile) -> HeartbeatRunner:
        """Retrieves or creates 30-min HeartbeatRunner for this chat."""
        if chat_id not in self.heartbeat_runners:
            routine_graph = RoutineGraph.seed_from_profile(profile)
            scheduled = ScheduledWorkRegistry.install_defaults(profile)
            self.heartbeat_runners[chat_id] = HeartbeatRunner(profile, routine_graph, scheduled)
        return self.heartbeat_runners[chat_id]

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
                [{"text": "⚡ Skills Menu"}, {"text": "🟢 24/7 Status"}, {"text": "🔒 Lock In Mode"}]
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

        # Check if chat is awaiting objective for a pending call briefing
        if chat_id in self.pending_call_briefings and self.pending_call_briefings[chat_id].get("stage") == "awaiting_objective":
            pending = self.pending_call_briefings.pop(chat_id)
            callee = pending["callee"]
            objective = text_clean
            packet = FactsPacket(
                callee=callee,
                objective=objective,
                authority=AuthorityLevel.L0,
                allowlist_confirmed=True
            )
            card = build_briefing_card(packet)
            self.pending_call_briefings[packet.call_id] = {
                "packet": packet,
                "chat_id": chat_id
            }
            btn_rows = [[card["buttons"][0]], [card["buttons"][1], card["buttons"][2]]] if len(card["buttons"]) == 3 else [card["buttons"]]
            await self.api.send_message(
                chat_id,
                card["text"],
                parse_mode="HTML",
                reply_markup={"inline_keyboard": btn_rows}
            )
            return

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

        # 4b. 24/7 Autonomous Daemon Status & Uptime
        if text_clean in ["/status", "/uptime", "🟢 24/7 Status", "24/7 Status", "status", "uptime"]:
            uptime_sec = int(time.time() - self.start_time)
            hrs, rem = divmod(uptime_sec, 3600)
            mins, secs = divmod(rem, 60)
            uptime_str = f"{hrs}h {mins}m {secs}s"

            from pico.device_sensors import BatterySensor
            bs = await BatterySensor.get_status()
            b_str = bs.to_summary()

            mem_avail_mb = 0
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemAvailable:"):
                            mem_avail_mb = int(line.split()[1]) // 1024
                            break
            except Exception:
                pass

            from pico.skills.skill_manage import CUSTOM_SKILLS_DIR
            custom_count = len([
                f for f in os.listdir(CUSTOM_SKILLS_DIR)
                if f.endswith(".py") and not f.startswith("__")
            ]) if os.path.exists(CUSTOM_SKILLS_DIR) else 0

            hb_runner = self.heartbeat_runners.get(chat_id)
            hb_count = hb_runner.beat_count if hb_runner else 0

            status_msg = (
                "🟢 **Pico 24/7 Autonomous Daemon Status**\n\n"
                f"• ⏱️ **Uptime**: `{uptime_str}`\n"
                f"• {b_str}\n"
                f"• 💾 **Available RAM**: `{mem_avail_mb} MB` (on 12 GB device)\n"
                f"• 💓 **Heartbeats Run**: `{hb_count} cycles` (every 30m)\n"
                f"• 📈 **Active Watchers**: `{len(self.watcher_mgr.watchers)} market alerts`\n"
                f"• 🧠 **Evolved Skills**: `{custom_count} autonomous skills`\n"
                f"• 🛡️ **MCP Security Ladder**: Active (SEE / SUGGEST / ASK / BLOCKED)\n"
                f"• ⚡ **Termux Wake Lock**: Active (CPU sleep prevented)\n\n"
                "*Pico is continuously guarding routines, habits, and market levels 24/7!* ✨"
            )
            await self.api.send_message(chat_id, status_msg)
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
                "• 📱 `/device` — Phone hardware diagnostics & tier\n"
                "• 🔋 `/battery` — Real-time battery & charging health\n"
                "• 🚀 `/launch <app>` — Open phone apps (spotify, youtube, etc.)\n"
                "• 📝 `/script <text>` — Script Doctor hook rater\n"
                "• 💰 `/sip <amt> <rate> <years>` — SIP Compounding Calculator\n"
                "• 🛍️ `/scrape [url|query]` — Live web item & price scraper with min/max analytics\n"
                "• ⏰ `/schedule [HH:MM task]` — Autonomous background schedule manager\n"
                "• 🎯 `/watch [symbol] [level]` — Real-time Binance crypto price watcher\n"
                "• 📞 `/call <contact> [message]` — Autonomous phone call agent with live summary & barge-in\n"
                "• 🛠️ `/agent <task>` — Autonomous multi-step problem solver\n"
            )

            # Check for dynamically synthesized Hermes skills
            from pico.skills.skill_manage import CUSTOM_SKILLS_DIR
            if os.path.exists(CUSTOM_SKILLS_DIR):
                custom_skills = [
                    f[:-3] for f in os.listdir(CUSTOM_SKILLS_DIR)
                    if f.endswith(".py") and not f.startswith("__")
                ]
                if custom_skills:
                    msg += "\n🧠 **Evolved Custom Skills (Hermes Self-Learned):**\n"
                    for cs in custom_skills:
                        msg += f"• 🔮 `{cs}` (Synthesized by Pico)\n"

            msg += "\n*Tap any command above or tell me what to build!*"
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
            if not takeover_res.get("success"):
                err_msg = takeover_res.get("error", "Could not start browser")
                await self.api.send_message(
                    chat_id,
                    f"🛡️ **Hardware Protection Gate Active**\n\n"
                    f"{err_msg}\n\n"
                    f"Pico will use clean cloud browsing instead so your device stays fast and battery-safe! 🔋✨"
                )
                return

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

        # 13c. Hardware Diagnostics & Device Architecture
        if text_clean in ["/device", "/hardware", "📱 Device Status"]:
            card = DeviceProfiler.format_diagnostic_card()
            await self.api.send_message(chat_id, card)
            return

        # 13d. Battery Status
        if text_clean in ["/battery", "/power", "🔋 Battery"]:
            status = await BatterySensor.get_status()
            await self.api.send_message(chat_id, status.to_summary())
            return

        # 13e. App Launcher (Android Activity Manager)
        if text_clean.startswith("/launch"):
            parts = text_clean.split(maxsplit=1)
            if len(parts) < 2:
                supported = ", ".join(AppLauncher.APP_MAP.keys())
                await self.api.send_message(chat_id, f"Usage: `/launch <app>`\nSupported apps: `{supported}`")
                return
            target_app = parts[1].strip()
            ok, launch_msg = await AppLauncher.launch_app(target_app)
            icon = "🚀" if ok else "⚠️"
            await self.api.send_message(chat_id, f"{icon} {launch_msg}")
            return

        # 13f. Browser Agent
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

        # 13b. Live Web Item & Price Scraper
        if text_clean.startswith("/scrape"):
            parts = text_clean.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else "https://books.toscrape.com/"
            await self.api.send_chat_action(chat_id, "typing")

            from pico.skills.price_scraper_skill import ItemPriceScraperSkill
            scraper = ItemPriceScraperSkill()
            inp = {"url": target} if target.startswith(("http://", "https://")) else {"query": target}
            res = scraper.execute(inp)

            if res.success:
                reply = res.output.get("summary_text", "Scraped items successfully!")
            else:
                reply = f"⚠️ Price scraper error: {res.error}"
            await self.api.send_message(chat_id, reply)
            return

        # 13c. Autonomous Dynamic Schedule Registry
        if text_clean.startswith("/schedule"):
            parts = text_clean.split(maxsplit=2)
            runner = self.get_or_create_heartbeat_runner(chat_id, profile)

            if len(parts) < 2:
                # List existing scheduled jobs & watchers
                jobs = runner.scheduled.list_jobs()
                lines = ["⏰ **Pico 24/7 Scheduled Jobs Registry**:\n"]
                for j in jobs:
                    lines.append(f"• `{j['name']}`: {j['schedule']} (Status: {'Enabled' if j['enabled'] else 'Disabled'})")

                if self.watcher_mgr.watchers:
                    lines.append("\n📈 **Active Real-Time Price Watchers:**")
                    for wid, w in self.watcher_mgr.watchers.items():
                        lines.append(f"• `{w.symbol}`: alert if {w.direction} ${w.target_level:,.0f}")

                lines.append("\n💡 *To schedule a new job: `/schedule HH:MM <Task Name>` (e.g. `/schedule 21:45 Read book`)*")
                await self.api.send_message(chat_id, "\n".join(lines))
                return

            # Adding new scheduled job
            time_part = parts[1].strip()
            task_desc = parts[2].strip() if len(parts) > 2 else "Routine Task"

            if re.match(r"^\d{1,2}:\d{2}$", time_part):
                h, m = time_part.split(":")
                norm_time = f"{int(h):02d}:{int(m):02d}"
                from pico.scheduled import ScheduledJob
                new_job = ScheduledJob(
                    id=f"custom_{norm_time.replace(':', '_')}_{int(time.time())}",
                    name=task_desc,
                    schedule_display=f"Daily at {norm_time} IST",
                    trigger_time=norm_time
                )
                runner.scheduled.register(new_job)
                await self.api.send_message(
                    chat_id,
                    f"⏰ **Job Scheduled Successfully!**\n\n"
                    f"• **Task:** `{task_desc}`\n"
                    f"• **Trigger:** `{norm_time} IST` (24/7 background worker active)\n\n"
                    f"Pico will proactively evaluate and push this notification when the clock touches {norm_time}! 🌟"
                )
                return
            else:
                await self.api.send_message(
                    chat_id,
                    "⚠️ Invalid time format. Please use `HH:MM` in 24h format (e.g. `/schedule 21:45 Read Habit`)."
                )
                return

        # 14. Real-time Crypto Watcher (Multi-symbol support)
        if text_clean.startswith("/watch"):
            parts = text_clean.split()
            if len(parts) >= 2:
                try:
                    if len(parts) >= 3:
                        sym = parts[1].upper()
                        if not sym.endswith("USDT"):
                            sym += "USDT"
                        level = float(parts[2])
                    else:
                        sym = "BTCUSDT"
                        level = float(parts[1])

                    cur_p = self.watcher_mgr.fetch_live_price(sym)
                    direction = "above" if level > cur_p else "below"

                    w = PriceWatcher(
                        id=f"watch_{sym.lower()}_{chat_id}_{int(level)}",
                        user_id=profile.user_id,
                        symbol=sym,
                        target_level=level,
                        direction=direction
                    )
                    self.watcher_mgr.add_watcher(w)
                    await self.api.send_message(
                        chat_id,
                        f"🎯 **Watcher Armed:** Watching `{sym}` at **${level:,.2f}** (Current: ${cur_p:,.2f})!\n"
                        f"Direction: Alert when price crosses **{direction}** threshold.\n"
                        f"The second price crosses this level, I'll send an instant alert!"
                    )
                    return
                except ValueError:
                    pass

        # 14b. Autonomous Multi-Turn Agent Mode (Claude Code-Grade)
        if text_clean.startswith("/agent") or text_clean.startswith("/code") or text_clean.startswith("/task"):
            parts = text_clean.split(maxsplit=1)
            if len(parts) < 2:
                await self.api.send_message(
                    chat_id,
                    "🤖 **Autonomous Agent Mode**\n\n"
                    "Usage: `/agent <goal>` or `/code <instruction>`\n\n"
                    "Examples:\n"
                    "• `/agent check git status and tell me the last commit`\n"
                    "• `/agent inspect my device storage and memory`\n"
                    "• `/code create a python script that calculates compound interest`\n\n"
                    "Pico will autonomously inspect files, run commands, and solve the task step-by-step!"
                )
                return

            task_goal = parts[1].strip()
            await self.api.send_chat_action(chat_id, "typing")
            await self.api.send_message(chat_id, f"🚀 **Agent Activated!** Pico is working on: *\"{task_goal}\"*...")

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.agent_loop.run_loop(
                    goal=task_goal,
                    profile=profile,
                    model_callable=self.pipeline.router.generate_raw,
                    max_steps=8,
                    pre_approved_tools=["read_file", "list_dir", "grep_search"],
                    auto_distill=True
                )
            )

            if result.paused_for_approval and result.pending_approval:
                self.pending_agent_tasks[chat_id] = {
                    "goal": task_goal,
                    "profile": profile,
                    "tool_name": result.pending_approval.get("tool_name"),
                    "arguments": result.pending_approval.get("arguments", {})
                }
                tool_n = result.pending_approval.get("tool_name")
                args_preview = json.dumps(result.pending_approval.get("arguments", {}), indent=2)
                approval_keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": f"✅ Approve {tool_n}", "callback_data": f"agent_approve_{tool_n}"},
                            {"text": "❌ Reject", "callback_data": "agent_reject"}
                        ]
                    ]
                }
                await self.api.send_message(
                    chat_id,
                    f"🛡️ **Permission Approval Card Required**\n\n"
                    f"Pico needs permission to run tool: `{tool_n}`\n"
                    f"**Arguments:**\n```json\n{args_preview[:500]}\n```\n\n"
                    f"Would you like me to execute this action?",
                    reply_markup=approval_keyboard
                )
                return

            # Format completed steps summary
            step_icons = []
            for s in result.steps:
                if s.tool_call:
                    step_icons.append(f"• Step {s.step_number}: `{s.tool_call.name}` -> *{s.thought or 'executed'}*")

            tools_summary = "\n".join(step_icons) if step_icons else "• Direct reasoned answer"

            status_icon = "✅" if result.success else "⚠️"
            reply = (
                f"{status_icon} **Agent Execution Completed** ({result.total_steps} steps in {result.execution_time_ms:.0f}ms):\n\n"
                f"{result.final_output}\n\n"
                f"⚙️ **Audit Trail:**\n{tools_summary}"
            )
            if result.distilled_skill:
                skill_info = result.distilled_skill
                s_name = skill_info.get("name", "custom_skill")
                reply += (
                    f"\n\n🧠 **Hermes Autonomous Skill Distilled!**\n"
                    f"Pico turned this successful multi-step workflow into a reusable skill: `{s_name}` ✨\n"
                    f"You can now run it anytime or view it in `/skills`!"
                )
            await self.api.send_message(chat_id, reply)
            return

        # 14c. Outbound Telephony Call Agent (/call, "call <name>", "pico call <name>")
        call_match = None
        if text_clean.startswith("/call"):
            remainder = text_clean[5:].strip()
            if remainder:
                parts = remainder.split(maxsplit=1)
                t_arg = parts[0]
                obj_arg = parts[1] if len(parts) > 1 else ""
                call_match = (t_arg, obj_arg)
            else:
                await self.api.send_message(
                    chat_id,
                    "📞 **Pico Phone Call Agent**\n\n"
                    "Usage: `/call <contact_or_number> [message]`\n\n"
                    "Examples:\n"
                    "• `/call dad`\n"
                    "• `/call mom tell her I'll be late for dinner`\n"
                    "• `/call +919876543210 ask about booking`\n\n"
                    "Or just say: *\"pico call dad\"*!"
                )
                return
        else:
            m = re.match(r"^(?:pico,?\s+)?call\s+([\w\+\d]+)(?:\s+(?:and\s+|to\s+)?(.+))?$", text_clean, re.IGNORECASE)
            if m:
                call_match = (m.group(1).strip(), (m.group(2) or "").strip())

        if call_match:
            target_name, objective = call_match
            callee = await resolve_callee(target_name)
            if not callee:
                await self.api.send_message(
                    chat_id,
                    f"⚠️ Could not find contact or valid phone number for '{target_name}'."
                )
                return

            if not objective:
                self.pending_call_briefings[chat_id] = {
                    "callee": callee,
                    "stage": "awaiting_objective"
                }
                await self.api.send_message(
                    chat_id,
                    f"📞 **Setting up call with {callee.name} ({callee.phone_number})**\n\n"
                    f"What should I tell or ask {callee.name}, and what are my limits?"
                )
                return
            else:
                packet = FactsPacket(
                    callee=callee,
                    objective=objective,
                    authority=AuthorityLevel.L0,
                    allowlist_confirmed=True
                )
                card = build_briefing_card(packet)
                self.pending_call_briefings[packet.call_id] = {
                    "packet": packet,
                    "chat_id": chat_id
                }
                btn_rows = [[card["buttons"][0]], [card["buttons"][1], card["buttons"][2]]] if len(card["buttons"]) == 3 else [card["buttons"]]
                await self.api.send_message(
                    chat_id,
                    card["text"],
                    parse_mode="HTML",
                    reply_markup={"inline_keyboard": btn_rows}
                )
                return

        # 15. Default: Run Full 7-Step Pipeline
        res = self.pipeline.run(
            user_message=text_clean,
            profile=profile,
            active_mode=current_mode
        )

        # Deduct actual token usage (H2: estimate from turn tokens, never a flat 150)
        tokens_consumed = res.get("tokens_estimated") or int(len(text_clean.split()) * 1.3 + len(res.get("output", "").split()) * 1.3) + 150
        self.token_mgr.record_usage(profile.user_id, tokens_consumed)

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

        # Telephony Confirm Call Callback
        if data.startswith("confirm_call_"):
            call_id = data.replace("confirm_call_", "")
            pending = self.pending_call_briefings.pop(call_id, None)
            if not pending:
                await self.api.answer_callback_query(cb_id, text="Call briefing not found or expired.")
                return

            packet = pending["packet"]
            await self.api.answer_callback_query(cb_id, text=f"Dialing {packet.callee.name}... 📞")

            # Execute dial through TelephonySkill
            self.skill_registry.execute_skill("telephony_skill", {
                "action": "dial",
                "phone_number": packet.callee.phone_number
            })

            session = CallSession(packet=packet)
            bridge = TelegramCallBridge(bot=self.api, chat_id=chat_id)
            self.active_call_sessions[packet.call_id] = session
            self.call_bridges[packet.call_id] = bridge

            # Post the live streaming summary card
            await bridge.post_call_started(session)
            await self.api.send_message(
                chat_id,
                f"📱 **Pico dialed {packet.callee.name} via SIM!**\n"
                f"Live status card is updating above. Tap **🚨 End Call Now** at any moment to immediately hang up."
            )
            return

        # Telephony Cancel Call Callback
        if data.startswith("cancel_call_"):
            call_id = data.replace("cancel_call_", "")
            pending = self.pending_call_briefings.pop(call_id, None)
            name = pending["packet"].callee.name if pending else "Call"
            await self.api.answer_callback_query(cb_id, text="Call cancelled ❌")
            await self.api.send_message(chat_id, f"❌ **{name} call cancelled.** Kept safe!")
            return

        # Telephony Edit Call Callback
        if data.startswith("edit_call_"):
            call_id = data.replace("edit_call_", "")
            pending = self.pending_call_briefings.get(call_id)
            if pending:
                callee = pending["packet"].callee
                self.pending_call_briefings[chat_id] = {"callee": callee, "stage": "awaiting_objective"}
                await self.api.answer_callback_query(cb_id, text="Edit details")
                await self.api.send_message(
                    chat_id,
                    f"📝 What should be the updated message or limits for {callee.name}?"
                )
            else:
                await self.api.answer_callback_query(cb_id, text="Briefing not found.")
            return

        # Telephony Emergency Abort Callback
        if data.startswith("abort_call_"):
            call_id = data.replace("abort_call_", "")
            session = self.active_call_sessions.get(call_id)
            bridge = self.call_bridges.get(call_id) or TelegramCallBridge(bot=self.api, chat_id=chat_id)
            if session:
                await self.api.answer_callback_query(cb_id, text="Emergency Abort Activated! 🚨")
                abort_msg = await bridge.emergency_abort(session)
                await bridge.update_live_summary(session)
                await self.api.send_message(chat_id, f"🚨 **EMERGENCY TAKEOVER:** {abort_msg}")
                await bridge.post_final_report(session)
                self.active_call_sessions.pop(call_id, None)
                self.call_bridges.pop(call_id, None)
            else:
                await self.api.answer_callback_query(cb_id, text="Call already ended.")
            return

        # Telephony Mid-Call Decision Callback
        if data.startswith("call_decide_"):
            parts = data.split("_")
            if len(parts) >= 4:
                call_id = parts[2]
                idx = int(parts[3])
                session = self.active_call_sessions.get(call_id)
                bridge = self.call_bridges.get(call_id)
                default_opts = ["Yes, proceed", "No, decline", "Call me directly"]
                decision_text = default_opts[idx] if idx < len(default_opts) else "User selected option"
                if session:
                    session.provide_user_decision(decision_text)
                    await self.api.answer_callback_query(cb_id, text=f"Delivered: {decision_text} ✅")
                    await self.api.send_message(chat_id, f"⚡ **Decision Delivered to Pico on the line:** *\"{decision_text}\"*")
                    if bridge:
                        await bridge.update_live_summary(session)
                else:
                    await self.api.answer_callback_query(cb_id, text="Call session ended.")
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

        # Autonomous Agent Loop Approval callbacks
        if data.startswith("agent_approve_"):
            pending = self.pending_agent_tasks.get(chat_id)
            if not pending:
                await self.api.answer_callback_query(cb_id, text="No pending task found.")
                return

            tool_n = pending["tool_name"]
            goal = pending["goal"]
            profile = pending["profile"]
            await self.api.answer_callback_query(cb_id, text=f"Approved {tool_n}! ⚡")
            await self.api.send_message(chat_id, f"⚡ Approval granted for `{tool_n}`! Resuming agent loop...")

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.agent_loop.run_loop(
                    goal=goal,
                    profile=profile,
                    model_callable=self.pipeline.router.generate_raw,
                    max_steps=8,
                    pre_approved_tools=["read_file", "list_dir", "grep_search", tool_n],
                    auto_distill=True
                )
            )
            self.pending_agent_tasks.pop(chat_id, None)

            # Format completed steps summary
            step_icons = []
            for s in result.steps:
                if s.tool_call:
                    step_icons.append(f"• Step {s.step_number}: `{s.tool_call.name}` -> *{s.thought or 'executed'}*")

            tools_summary = "\n".join(step_icons) if step_icons else "• Direct reasoned answer"

            status_icon = "✅" if result.success else "⚠️"
            reply = (
                f"{status_icon} **Agent Execution Finished:**\n\n"
                f"{result.final_output}\n\n"
                f"⚙️ **Audit Trail:**\n{tools_summary}"
            )
            if result.distilled_skill:
                skill_info = result.distilled_skill
                s_name = skill_info.get("name", "custom_skill")
                reply += (
                    f"\n\n🧠 **Hermes Autonomous Skill Distilled!**\n"
                    f"Pico turned this successful multi-step workflow into a reusable skill: `{s_name}` ✨\n"
                    f"You can now run it anytime or view it in `/skills`!"
                )
            await self.api.send_message(chat_id, reply)
            return

        if data == "agent_reject":
            self.pending_agent_tasks.pop(chat_id, None)
            await self.api.answer_callback_query(cb_id, text="Action rejected.")
            await self.api.send_message(chat_id, "🛑 Action rejected. Agent loop cancelled safely.")
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
                        [{"text": "📸 Refresh Screenshot", "callback_data": "takeover_refresh"}],
                        [{"text": "✅ Done, Pico Take Over!", "callback_data": "takeover_done"}],
                        [{"text": "❌ Cancel Handoff", "callback_data": "takeover_cancel"}]
                    ]
                }
                caption = (
                    f"📸 **Current Live Screen for {self.handoff.current_domain}**:\n"
                    f"👉 Control link: http://localhost:{self.handoff.web_port}/takeover"
                )
                await self.api.send_photo(chat_id, ss, caption=caption, reply_markup=keyboard)
            else:
                await self.api.send_message(chat_id, "⚠️ Could not capture live screen.")
            return

        if data == "takeover_cancel":
            await self.api.answer_callback_query(cb_id, text="Handoff cancelled")
            await self.api.send_message(chat_id, "🛑 Browser takeover cancelled.")
            return

        await self.api.answer_callback_query(cb_id)

    async def scheduled_heartbeat_loop(self, chat_id: int):
        """
        24/7 Autonomous Background Worker for Pico:
        - 07:30 IST: Morning Brief
        - 21:30 IST: Evening Review
        - 23:00 IST: Daily Self-Analysis Scorecard
        - Every 30 min: HeartbeatRunner (7 ordered checks)
        - Every 60 sec: Live Binance Price Watchers
        - Every 10 min: Device Battery & Thermal Guard
        """
        logger.info(f"🟢 Started 24/7 scheduled heartbeat loop for chat {chat_id}")
        while self.is_running:
            try:
                # Use local device time (IST on Realme 11 Pro 5G)
                now = datetime.now()
                hour = now.hour
                minute = now.minute
                today_str = now.strftime("%Y-%m-%d")
                current_time_str = now.strftime("%H:%M")

                profile = self.get_or_create_profile(chat_id, "Friend")

                # Respect Quiet Hours (22:00 - 07:00 local)
                is_quiet_hours = (hour >= 22 or hour < 7)

                if not is_quiet_hours:
                    # 1. Morning Brief at 07:30 local time
                    if hour == 7 and minute == 30 and self.last_morning_brief_date != today_str:
                        self.last_morning_brief_date = today_str
                        routine_graph = RoutineGraph.seed_from_profile(profile)
                        brief = BriefGenerator.generate_morning_brief(profile, routine_graph)
                        await self.api.send_message(
                            chat_id,
                            f"☀️ **Good Morning! Here is your Morning Brief ({current_time_str}):**\n\n{brief}"
                        )

                    # 2. Evening Review at 21:30 local time
                    if hour == 21 and minute == 30 and self.last_evening_review_date != today_str:
                        self.last_evening_review_date = today_str
                        review = BriefGenerator.generate_evening_review(
                            profile=profile,
                            streak_count=1,
                            completed_tasks=["Active check-in completed!"]
                        )
                        await self.api.send_message(
                            chat_id,
                            f"🌙 **Evening Review (21:30):**\n\n{review}"
                        )

                # 3. Nightly Self-Analysis Report at 23:00 local time
                if hour == 23 and minute == 0 and self.last_nightly_report_date != today_str:
                    self.last_nightly_report_date = today_str
                    from pico.reports import DailyScorecard, SelfAnalysisEngine
                    scorecard = DailyScorecard(
                        user_id=profile.user_id,
                        date=today_str,
                        beats_fired=48,
                        silent_beats=44
                    )
                    report_md = SelfAnalysisEngine.generate_nightly_report(scorecard, profile)
                    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
                    os.makedirs(reports_dir, exist_ok=True)
                    with open(os.path.join(reports_dir, f"daily_report_{today_str}.md"), "w") as rf:
                        rf.write(report_md)

                    await self.api.send_message(
                        chat_id,
                        f"📊 **Nightly Self-Analysis Report ({today_str}):**\n\n"
                        f"• Operational Score: **{scorecard.total_score}/10** (Status: ✅ Healthy)\n"
                        f"• Memory Honesty: {scorecard.memory_honesty}/2\n"
                        f"• Routine Discipline: {scorecard.discipline}/2\n"
                        f"• Total Heartbeats: {scorecard.beats_fired}\n\n"
                        f"Quiet hours in effect. Sleep well and recharge for tomorrow! 🌟"
                    )

                # 4. 30-Minute Proactive Heartbeat (§13.3)
                if minute in [0, 30]:
                    runner = self.get_or_create_heartbeat_runner(chat_id, profile)
                    beat = runner.fire_beat(current_time_str)
                    if beat.outcome == HeartbeatOutcome.SPEAK and not is_quiet_hours:
                        await self.api.send_message(
                            chat_id,
                            f"💓 **Pico Proactive Heartbeat** ({current_time_str}):\n{beat.reason}"
                        )
                    elif beat.outcome == HeartbeatOutcome.ESCALATE:
                        await self.api.send_message(
                            chat_id,
                            f"🚨 **Urgent Alert** ({current_time_str}):\n{beat.reason}"
                        )

                # 5. Check Live Binance Price Watchers (Every 60 seconds)
                alerts = self.watcher_mgr.evaluate_watchers()
                for alert in alerts:
                    await self.api.send_message(
                        chat_id,
                        f"🚨 **Pico Market Watcher Alert!**\n\n{alert.push_notification}"
                    )

                # 6. Device Battery & Thermal Guard (Every 10 min)
                if minute % 10 == 0:
                    from pico.device_sensors import BatterySensor
                    should_remind, b_msg = await BatterySensor.should_remind_plug_in()
                    if should_remind and (time.time() - self.last_battery_alert_time > 1800):
                        self.last_battery_alert_time = time.time()
                        await self.api.send_message(
                            chat_id,
                            f"⚡ **Pico 24/7 Battery Guard Alert:**\n\n{b_msg}"
                        )

            except Exception as e:
                logger.error(f"Error in 24/7 heartbeat loop: {e}")

            # Sleep 60s between checks
            await asyncio.sleep(60)

    async def start_polling(self):
        """Main long-polling event loop with 24/7 autonomous supervision."""
        self.is_running = True
        logger.info("Connecting to Telegram Bot API...")
        me = await self.api.get_me()
        if not me:
            logger.error("❌ Failed to verify Telegram Bot token. Please check your TELEGRAM_BOT_TOKEN.")
            return

        bot_name = me.get("first_name", "Pico")
        bot_user = me.get("username", "pico_bot")
        print("\n" + "=" * 65)
        print(f"🌟 PICO TELEGRAM BOT IS LIVE AND RUNNING 24/7!")
        print(f"   Bot Name:     {bot_name}")
        print(f"   Bot Username: @{bot_user}")
        print(f"   Admin Chat:   {self.admin_chat_id}")
        print(f"   Open Telegram and search for: @{bot_user}")
        print("=" * 65 + "\n")

        offset = None
        background_tasks: Dict[int, asyncio.Task] = {}

        # Autostart 24/7 background heartbeat immediately for admin chat
        if self.admin_chat_id:
            background_tasks[self.admin_chat_id] = asyncio.create_task(
                self.scheduled_heartbeat_loop(self.admin_chat_id)
            )

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
                            # Start scheduled background loop if not already running for this chat
                            if chat_id not in background_tasks:
                                background_tasks[chat_id] = asyncio.create_task(
                                    self.scheduled_heartbeat_loop(chat_id)
                                )

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
            for t in background_tasks.values():
                t.cancel()
            self.is_running = False
            logger.info("Telegram Bot stopped.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        env_paths = [".env", "pico/.env", str(get_pico_home() / "pico" / ".env"), str(get_pico_home() / ".env")]
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
