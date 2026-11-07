"""Call Session State Machine, CRBT Filter and Mid-Call Bridge for Pico Telephony."""

import re
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from telephony.briefing import FactsPacket, get_opening_disclosure_line
from telephony.commitment_checker import CommitmentChecker
from telephony.audio_bridge import AudioBridge

class CallStatus(str, Enum):
    DIALING = "DIALING"
    WAITING_HUMAN = "WAITING_HUMAN"   # Waiting for caller greeting / CRBT tune playing
    CONNECTED = "CONNECTED"           # Active conversation
    STALLED = "STALLED"               # Paused on hold waiting for user Telegram decision
    ENDED = "ENDED"

class CallSession:
    """
    Manages an individual outbound call session state, dialogue progression,
    CRBT detection, mid-call stalls, and live summary logging.
    """

    HUMAN_GREETINGS = [
        r"\bhello\b",
        r"^(?:hi|hey)\b",
        r"\b(?:hi|hey)\s+(?:there|pico|ayush|sir|bhai|uncle|ji)\b",
        r"\bhaan\s+(?:bol|batao|ji|bhai)?\b",
        r"\b(?:haanji|namaste|namaskar|pranam)\b",
        r"\b(?:kahiye|bataiye|bolo)\b",
        r"\b(?:who is|kaun|kon)\s+(?:speaking|calling|this|hai|bol raha)\b",
        r"\bgood\s+(?:morning|afternoon|evening)\b",
        r"\byes\s+(?:please|speaking)?\b",
    ]

    def __init__(
        self,
        packet: FactsPacket,
        commitment_checker: Optional[CommitmentChecker] = None,
        audio_bridge: Optional[AudioBridge] = None,
        user_name: str = "Ayush"
    ):
        self.packet = packet
        self.commitment_checker = commitment_checker or CommitmentChecker()
        self.audio_bridge = audio_bridge or AudioBridge()
        self.user_name = user_name
        
        self.status: CallStatus = CallStatus.WAITING_HUMAN
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        
        self.transcript: List[Dict[str, Any]] = []
        self.summary_bullets: List[str] = []
        
        self.pending_question: Optional[str] = None
        self.user_decision: Optional[str] = None
        self.stall_start_time: Optional[float] = None

    def is_human_greeting(self, text: str) -> bool:
        """Check if incoming transcription matches a human greeting rather than carrier music/CRBT."""
        if not text:
            return False
        clean = text.lower().strip()
        for pattern in self.HUMAN_GREETINGS:
            if re.search(pattern, clean):
                return True
        return False

    async def handle_incoming_transcript(self, caller_text: str) -> str:
        """
        Process a transcribed turn from the callee.
        Gates opening turn on human greeting to filter out Indian CRBT tunes.
        """
        if not caller_text:
            return ""

        caller_clean = caller_text.strip()
        
        # 1. In WAITING_HUMAN state: wait until real human greeting
        if self.status == CallStatus.WAITING_HUMAN:
            if not self.is_human_greeting(caller_clean):
                # Detected ringback song / noise - stay silent!
                return ""
            
            # Transition to active conversation
            self.status = CallStatus.CONNECTED
            self.transcript.append({
                "role": "callee",
                "text": caller_clean,
                "timestamp": time.time()
            })
            self.add_summary_bullet(f"Call answered by {self.packet.callee.name}.")

            # Speak mandatory opening disclosure
            opening = get_opening_disclosure_line(self.packet, user_name=self.user_name)
            checked = self.commitment_checker.verify_utterance(opening, self.packet)
            reply = checked.sanitized_text or opening
            
            self.transcript.append({
                "role": "assistant",
                "text": reply,
                "timestamp": time.time()
            })
            self.add_summary_bullet(f"Pico introduced call: '{self.packet.objective}'")
            return reply

        # 2. In CONNECTED state: process normal dialogue turn
        if self.status == CallStatus.CONNECTED:
            self.transcript.append({
                "role": "callee",
                "text": caller_clean,
                "timestamp": time.time()
            })
            # Check for simple acknowledgment
            return f"Understood, thank you. Regarding {self.packet.objective}, I will note that down."

        return ""

    async def trigger_stall(self, question: str) -> str:
        """
        Initiate a mid-call hold while waiting for user decision over Telegram.
        """
        self.status = CallStatus.STALLED
        self.pending_question = question
        self.stall_start_time = time.time()
        
        stall_phrase = "One second, let me check that note from Ayush."
        self.transcript.append({
            "role": "assistant",
            "text": stall_phrase,
            "timestamp": time.time(),
            "type": "stall"
        })
        self.add_summary_bullet(f"Paused for user decision: '{question}'")
        return stall_phrase

    def provide_user_decision(self, decision: str) -> None:
        """Record the user's answer from Telegram callback."""
        self.user_decision = decision

    async def resolve_pending_decision(self) -> str:
        """Resume dialogue with user's decision."""
        if not self.user_decision:
            return self.apply_timeout_default()
        
        answer = self.user_decision
        reply = f"Thanks for waiting. Ayush says: {answer}."
        checked = self.commitment_checker.verify_utterance(reply, self.packet)
        final_reply = checked.sanitized_text or reply
        
        self.status = CallStatus.CONNECTED
        self.pending_question = None
        self.user_decision = None
        self.stall_start_time = None
        
        self.transcript.append({
            "role": "assistant",
            "text": final_reply,
            "timestamp": time.time()
        })
        self.add_summary_bullet(f"User decision delivered: '{answer}'")
        return final_reply

    def apply_timeout_default(self) -> str:
        """Pre-agreed fallback when user is unreachable during hold."""
        fallback = "Ayush isn't able to confirm right now, so he will text you directly about that. Is there anything else?"
        self.status = CallStatus.CONNECTED
        self.pending_question = None
        self.user_decision = None
        self.stall_start_time = None
        
        self.transcript.append({
            "role": "assistant",
            "text": fallback,
            "timestamp": time.time(),
            "type": "timeout_default"
        })
        self.add_summary_bullet("Timeout expired: relayed callback promise.")
        return fallback

    async def handle_callee_interruption(self, caller_cut_in: str) -> None:
        """Handle callee cutting in while Pico was speaking."""
        self.audio_bridge.flush_playback()
        self.transcript.append({
            "role": "callee",
            "text": caller_cut_in,
            "timestamp": time.time(),
            "interrupted": True
        })
        self.add_summary_bullet(f"Callee interrupted: '{caller_cut_in}'")

    def add_summary_bullet(self, bullet: str) -> None:
        """Add a summary milestone to the live card feed."""
        self.summary_bullets.append(bullet)

    def end_call(self, reason: str = "completed") -> None:
        """Conclude the call session."""
        self.status = CallStatus.ENDED
        self.end_time = time.time()
        self.add_summary_bullet(f"Call ended ({reason}).")
