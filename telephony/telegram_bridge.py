"""Telegram Live Summary Card, Mid-Call Ping and Emergency Abort Bridge for Pico."""

import time
import logging
from typing import Optional, List, Dict, Any, Tuple
from telephony.call_session import CallSession, CallStatus

logger = logging.getLogger(__name__)

class TelegramCallBridge:
    """
    Handles live in-flight status streaming, mid-call Telegram approval cards,
    and emergency takeover controls during active phone calls.
    """

    def __init__(self, bot: Any = None, chat_id: Optional[int] = None, min_edit_interval: float = 1.5):
        self.bot = bot
        self.chat_id = chat_id
        self.min_edit_interval = min_edit_interval
        self._last_edit_time: float = 0.0
        self._live_message_id: Optional[int] = None

    def _format_duration(self, seconds: float) -> str:
        mins, secs = divmod(int(seconds), 60)
        return f"{mins:02d}:{secs:02d}"

    def format_summary_card(self, session: CallSession) -> Tuple[str, List[List[Dict[str, str]]]]:
        """
        Format the single continuously-edited live summary card.
        """
        elapsed = time.time() - session.start_time
        duration_str = self._format_duration(elapsed)
        status_label = session.status.value.replace("_", " ").title()

        bullets_str = "\n".join(f"• {b}" for b in session.summary_bullets[-5:]) if session.summary_bullets else "• Call initiated..."

        text = (
            f"📞 <b>In Call with: {session.packet.callee.name}</b>\n"
            f"📱 <code>{session.packet.callee.phone_number}</code>\n"
            f"⏱ <b>Duration:</b> {duration_str} | <b>Status:</b> {status_label}\n\n"
            f"📝 <b>Live Summary:</b>\n"
            f"{bullets_str}\n"
        )

        buttons = [
            [
                {
                    "text": "🚨 End Call Now",
                    "callback_data": f"abort_call_{session.packet.call_id}"
                }
            ]
        ]

        return text, buttons

    def format_mid_call_ping(
        self,
        session: CallSession,
        question: str,
        options: Optional[List[str]] = None,
        timeout_seconds: int = 45
    ) -> Tuple[str, List[List[Dict[str, str]]]]:
        """
        Format an urgent mid-call approval ping card with quick decision buttons.
        """
        opts = options or ["Yes, proceed", "No, decline", "Call me directly"]
        
        text = (
            f"⚠️ <b>URGENT MID-CALL APPROVAL</b>\n\n"
            f"👤 <b>Callee:</b> {session.packet.callee.name}\n"
            f"❓ <b>Question from callee:</b>\n"
            f"<i>\"{question}\"</i>\n\n"
            f"⏳ <b>Auto-default in {timeout_seconds}s:</b> Pico will politely state you are unreachable and will text back.\n\n"
            f"Tap an option to instruct Pico live on the line:"
        )

        buttons = []
        for i, opt in enumerate(opts):
            buttons.append([{
                "text": opt,
                "callback_data": f"call_decide_{session.packet.call_id}_{i}"
            }])
        
        buttons.append([{
            "text": "🚨 Hang Up",
            "callback_data": f"abort_call_{session.packet.call_id}"
        }])

        return text, buttons

    async def emergency_abort(self, session: CallSession) -> str:
        """
        Immediately drop and terminate an in-flight call session.
        """
        session.audio_bridge.flush_playback()
        session.end_call("emergency_abort_by_user")
        logger.info(f"Call {session.packet.call_id} aborted by user emergency takeover.")
        return f"Call with {session.packet.callee.name} was immediately aborted and terminated."

    def format_final_report(self, session: CallSession) -> str:
        """
        Format the final post-call report with key outcomes and full transcript.
        """
        elapsed = (session.end_time or time.time()) - session.start_time
        duration_str = self._format_duration(elapsed)

        milestones = "\n".join(f"• {b}" for b in session.summary_bullets)

        transcript_lines = []
        for turn in session.transcript:
            speaker = "Pico" if turn.get("role") == "assistant" else session.packet.callee.name
            transcript_lines.append(f"<b>{speaker}:</b> {turn.get('text', '')}")
        
        transcript_str = "\n".join(transcript_lines) or "<i>No speech recorded</i>"

        report = (
            f"✅ <b>CALL COMPLETED: {session.packet.callee.name}</b>\n"
            f"📱 <code>{session.packet.callee.phone_number}</code> | ⏱ <b>Duration:</b> {duration_str}\n"
            f"🎯 <b>Objective:</b> {session.packet.objective}\n\n"
            f"📋 <b>Key Milestones:</b>\n"
            f"{milestones}\n\n"
            f"📜 <b>Full Transcript:</b>\n"
            f"<blockquote expandable>{transcript_str}</blockquote>"
        )
        return report

    async def post_call_started(self, session: CallSession) -> Optional[int]:
        """
        Send the initial live summary card to Telegram and return the message_id.
        """
        text, buttons = self.format_summary_card(session)
        reply_markup = {"inline_keyboard": buttons}
        if self.bot and self.chat_id:
            res = await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            if res and isinstance(res, dict) and "message_id" in res:
                self._live_message_id = res["message_id"]
            elif hasattr(res, "message_id"):
                self._live_message_id = res.message_id
            self._last_edit_time = time.time()
            return self._live_message_id
        return None

    async def update_live_summary(self, session: CallSession, bullet: Optional[str] = None) -> bool:
        """
        Update the single live summary card with rate limiting.
        """
        if bullet:
            session.add_summary_bullet(bullet)

        now = time.time()
        # Rate limit: do not edit more often than min_edit_interval unless call ended
        if session.status != CallStatus.ENDED and (now - self._last_edit_time) < self.min_edit_interval:
            return False

        text, buttons = self.format_summary_card(session)
        reply_markup = {"inline_keyboard": buttons}

        if self.bot and self.chat_id and self._live_message_id:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self._live_message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            self._last_edit_time = now
            return True
        return False

    async def trigger_mid_call_ping(
        self,
        session: CallSession,
        question: str,
        options: Optional[List[str]] = None,
        timeout_seconds: int = 45
    ) -> Optional[int]:
        """
        Send an urgent mid-call approval ping card to Telegram.
        """
        text, buttons = self.format_mid_call_ping(
            session=session,
            question=question,
            options=options,
            timeout_seconds=timeout_seconds
        )
        reply_markup = {"inline_keyboard": buttons}
        if self.bot and self.chat_id:
            res = await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            if res and isinstance(res, dict) and "message_id" in res:
                return res["message_id"]
            elif hasattr(res, "message_id"):
                return res.message_id
        return None

    async def post_final_report(self, session: CallSession) -> Optional[int]:
        """
        Send the completed call report with full transcript to Telegram.
        """
        report = self.format_final_report(session)
        if self.bot and self.chat_id:
            res = await self.bot.send_message(
                chat_id=self.chat_id,
                text=report,
                parse_mode="HTML"
            )
            if res and isinstance(res, dict) and "message_id" in res:
                return res["message_id"]
            elif hasattr(res, "message_id"):
                return res.message_id
        return None
