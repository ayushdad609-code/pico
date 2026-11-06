"""
The BTW Engine (Contextual Asks) for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§11 The BTW Engine).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from .models import PersonaPacket, Sensitivity, EmotionSensitivity, Fact, FactSource, FactStatus


@dataclass
class MemoryGap:
    """A wished-for fact registered in the Gap Registry (§11)."""
    id: str
    user_id: str
    topic: str
    fact_key: str
    question_template: str  # Must contain the reason inside: "...so next time I pick better"
    priority: int = 1
    sensitivity: Sensitivity = Sensitivity.PERSONAL
    attempts: int = 0
    status: str = "open"  # "open", "asked", "filled", "dropped"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BTWEngine:
    """
    Manages contextual asks without interrogating.
    Founder's rule: Never ask randomly. Ask only when the topic is raised,
    attached after value is delivered, and the answer goes into memory.
    """
    def __init__(self):
        self.gaps: Dict[str, MemoryGap] = {}
        self.daily_ask_count = 0
        self.last_ask_turn = -99  # Tracks outputs since last ask
        self.current_turn = 0
        self.pending_ask: Optional[MemoryGap] = None

    def register_gap(self, gap: MemoryGap):
        self.gaps[gap.id] = gap

    def seed_starter_bank_for_hobby(self, user_id: str, hobby: str):
        """Seeds starter BTW gaps from the hobby rulebook (§18)."""
        if hobby == "gym":
            self.register_gap(MemoryGap(
                id=f"gap_gym_protein_{user_id}",
                user_id=user_id,
                topic="gym",
                fact_key="protein_style",
                question_template="btw, do you take protein shakes or focus on whole foods? (So I calibrate your recovery nudges!)"
            ))
            self.register_gap(MemoryGap(
                id=f"gap_gym_injury_{user_id}",
                user_id=user_id,
                topic="gym",
                fact_key="old_injury_history",
                sensitivity=Sensitivity.SENSITIVE,
                question_template="btw, any old joint or back injuries I should watch out for during workouts? (Feel free to skip if you prefer!)"
            ))
        elif hobby == "trading":
            self.register_gap(MemoryGap(
                id=f"gap_trade_holding_{user_id}",
                user_id=user_id,
                topic="trading",
                fact_key="holding_style",
                question_template="btw, are you mostly a spot hodler or active swing trader? (Helps me know how fast to ping you!)"
            ))

    def evaluate_ask_gate(
        self,
        packet: PersonaPacket,
        current_topic: str,
        value_delivered: bool = True,
        is_p0_alert: bool = False
    ) -> Tuple[bool, Optional[MemoryGap]]:
        """
        The Ask Gate (ALL must pass per §11):
        1. Real value delivered first
        2. Topic genuinely raised
        3. <= 1 ask per output
        4. <= 3/day (resets daily at midnight)
        5. None in the last 3 outputs
        6. NEVER on P0 alerts, sad/tender talks, corrections, or disliked verdicts
        7. Attempts < 2
        8. ReactionPlan do_not vetoes absolutely
        """
        self.current_turn += 1

        # Midnight daily reset for asks
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if getattr(self, "last_ask_date", None) != today_str:
            self.daily_ask_count = 0
            self.last_ask_date = today_str

        # Rule 6: Absolute veto on P0 alerts
        if is_p0_alert:
            return False, None

        # Rule 6 & 8: Veto on tender/crisis emotions or do_not rules
        if packet.emotion_assessment.sensitivity in [EmotionSensitivity.TENDER, EmotionSensitivity.CRISIS]:
            return False, None

        if any("NO BTW" in rule for rule in packet.reaction_plan.do_not_list):
            return False, None

        # Rule 1: Must have delivered value
        if not value_delivered:
            return False, None

        # Rule 4: <= 3/day
        if self.daily_ask_count >= 3:
            return False, None

        # Rule 5: None in the last 3 outputs
        if (self.current_turn - self.last_ask_turn) <= 3:
            return False, None

        # Find a matching open gap for current topic
        for gap_id, gap in self.gaps.items():
            if gap.status == "open" and gap.attempts < 2:
                if gap.topic.lower() in current_topic.lower() or current_topic.lower() in gap.topic.lower():
                    # Gate Passed!
                    gap.attempts += 1
                    gap.status = "asked"
                    self.daily_ask_count += 1
                    self.last_ask_turn = self.current_turn
                    self.pending_ask = gap
                    return True, gap

        return False, None

    def capture_answer(self, user_message: str, user_id: str) -> Optional[Fact]:
        """
        Step 2 pre-check: captures answer to an open PendingAsk even mid-sentence (§11).
        """
        if not self.pending_ask:
            return None

        # Simple extraction of answer span
        gap = self.pending_ask
        self.pending_ask = None
        gap.status = "filled"

        fact = Fact(
            key=gap.fact_key,
            value=user_message.strip(),
            source=FactSource.CONTEXTUAL_ASK,
            sensitivity=gap.sensitivity,
            mode=gap.topic,
            status=FactStatus.COMMITTED
        )
        return fact
