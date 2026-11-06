"""
Streak Insurance Engine for Pico (Feature F2).
Proactively intervenes before a streak breaks with an honest micro-version (2-minute habit).
"""

from __future__ import annotations
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional, List
from pico.paths import get_default_db_path


# Curated 2-minute micro-habit contracts per launch hobby domain (§18 / F2)
MICRO_HABIT_CATALOG: Dict[str, Dict[str, str]] = {
    "gym": {
        "action": "Do 10 bodyweight squats or hold a 30-second plank",
        "rationale": "Keeps neuromuscular connection alive on zero-time days"
    },
    "coding": {
        "action": "Review 5 lines of code or commit a 1-line comment/fix",
        "rationale": "Maintains GitHub green square and builder mindset"
    },
    "study": {
        "action": "Review 2 key concepts or read 1 summary flashcard",
        "rationale": "Spaced repetition reinforcement without cognitive overload"
    },
    "trading": {
        "action": "Check 1 daily candlestick chart and note the major trend",
        "rationale": "Observational discipline without risking capital"
    },
    "content_creation": {
        "action": "Jot down 1 hook or headline idea in your notes",
        "rationale": "Seeds tomorrow's creative pipeline in 90 seconds"
    },
    "music": {
        "action": "Play or hum 1 scale/melody for 2 minutes",
        "rationale": "Preserves tactile finger memory and ear training"
    },
    "reading": {
        "action": "Read 1 full page or 2 paragraphs of your book",
        "rationale": "Defeats reading friction without fatigue"
    },
    "default": {
        "action": "Complete a 2-minute micro-action towards your 90-day goal",
        "rationale": "Preserves habit identity: 'I never miss two days in a row'"
    }
}


@dataclass
class StreakInsuranceSave:
    id: str
    user_id: str
    hobby: str
    saved_streak_count: int
    micro_action: str
    saved_at: str
    notes: str


class StreakInsuranceEngine:
    """Manages proactive streak protection and honest micro-session saves."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_default_db_path()
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS streak_insurance_saves (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        hobby TEXT NOT NULL,
                        saved_streak_count INTEGER NOT NULL,
                        micro_action TEXT NOT NULL,
                        saved_at TEXT NOT NULL,
                        notes TEXT
                    )
                """)
            conn.close()
        except Exception:
            pass

    def check_at_risk(
        self,
        current_hour: int,
        activity_logged_today: bool,
        current_streak: int
    ) -> bool:
        """Streak is at risk if after 20:00 (8 PM) and no activity was logged today."""
        if activity_logged_today:
            return False
        if current_streak <= 0:
            return False
        return 20 <= current_hour <= 23

    def get_insurance_proposal(self, hobby: str, current_streak: int) -> Dict[str, Any]:
        """Proposes a concrete 2-minute micro-action to save the streak before midnight."""
        h_key = hobby.lower() if hobby.lower() in MICRO_HABIT_CATALOG else "default"
        contract = MICRO_HABIT_CATALOG[h_key]
        return {
            "hobby": hobby,
            "current_streak": current_streak,
            "is_risk": True,
            "micro_action": contract["action"],
            "rationale": contract["rationale"],
            "proposal_message": (
                f"🛡️ **Streak Insurance Alert!**\n"
                f"Your {current_streak}-day {hobby.capitalize()} streak is at risk tonight!\n\n"
                f"Instead of watching it break, take the 2-minute Micro-Habit:\n"
                f"👉 **{contract['action']}**\n\n"
                f"Reply `/save-streak` once done to lock in your save honestly!"
            )
        }

    def claim_save(
        self,
        user_id: str,
        hobby: str,
        current_streak: int,
        micro_action_done: Optional[str] = None
    ) -> StreakInsuranceSave:
        """Locks in the saved streak and records it honestly in memory."""
        s_id = f"save_{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        action = micro_action_done or MICRO_HABIT_CATALOG.get(hobby.lower(), MICRO_HABIT_CATALOG["default"])["action"]
        notes = f"Streak #{current_streak + 1} saved via 2-minute micro-habit: '{action}'."

        record = StreakInsuranceSave(
            id=s_id,
            user_id=user_id,
            hobby=hobby,
            saved_streak_count=current_streak + 1,
            micro_action=action,
            saved_at=now_iso,
            notes=notes
        )

        try:
            conn = sqlite3.connect(self.db_path)
            with conn:
                conn.execute("""
                    INSERT INTO streak_insurance_saves (
                        id, user_id, hobby, saved_streak_count, micro_action, saved_at, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.id, record.user_id, record.hobby, record.saved_streak_count,
                    record.micro_action, record.saved_at, record.notes
                ))
            conn.close()
        except Exception:
            pass

        return record

    def list_saves(self, user_id: str) -> List[StreakInsuranceSave]:
        """Returns all streak saves logged for the user."""
        saves = []
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, hobby, saved_streak_count, micro_action, saved_at, notes
                FROM streak_insurance_saves WHERE user_id = ? ORDER BY saved_at DESC
            """, (user_id,))
            for r in cursor.fetchall():
                saves.append(StreakInsuranceSave(
                    id=r[0], user_id=r[1], hobby=r[2], saved_streak_count=r[3],
                    micro_action=r[4], saved_at=r[5], notes=r[6]
                ))
            conn.close()
        except Exception:
            pass
        return saves
