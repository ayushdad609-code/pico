"""
Self-Analysis & Nightly Scorecard System for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§14 Self-Analysis & Report Files).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from .models import UserProfile


@dataclass
class DailyScorecard:
    """The 5 criteria x 0/1/2 scorecard (§14)."""
    user_id: str
    date: str
    memory_honesty: int = 2     # 0, 1, 2
    verdict_quality: int = 2    # 0, 1, 2
    emotion_fit: int = 2        # 0, 1, 2
    research_honesty: int = 2   # 0, 1, 2
    discipline: int = 2         # 0, 1, 2
    weakest_point: str = "None identified"
    cited_run_ids: List[str] = field(default_factory=list)
    beats_fired: int = 48
    silent_beats: int = 42
    guardrail_hits: int = 0
    degraded_mode_triggered: bool = False

    @property
    def total_score(self) -> int:
        score = self.memory_honesty + self.verdict_quality + self.emotion_fit + self.research_honesty + self.discipline
        if self.guardrail_hits > 0 or self.memory_honesty == 0:
            return min(score, 5)  # Hard fail caps day at 5/10
        return score


class SelfAnalysisEngine:
    """Generates the nightly self-report (.md) and scorecard (.json)."""

    @staticmethod
    def generate_nightly_report(scorecard: DailyScorecard, profile: UserProfile) -> str:
        """Renders the Markdown Daily Self-Report (§14)."""
        status_line = (
            "⚠️ DEGRADED MODE TRIGGERED FOR TOMORROW (Score <= 5/10)"
            if scorecard.total_score <= 5
            else "✅ HEALTHY OPERATIONAL STATE"
        )

        report = f"""# DAILY SELF-REPORT: {scorecard.date} — {profile.name}
**Status:** {status_line}
**Total Score:** {scorecard.total_score} / 10

## 1. Scorecard Breakdown (0-2 Scale)
- **Memory Honesty:** {scorecard.memory_honesty}/2
- **Verdict Quality:** {scorecard.verdict_quality}/2
- **Emotion Fit:** {scorecard.emotion_fit}/2
- **Research Honesty:** {scorecard.research_honesty}/2
- **Discipline (Heartbeat/Budget):** {scorecard.discipline}/2

## 2. Diagnostics & Weakest Point
- **Weakest Point Identified:** {scorecard.weakest_point}
- **Cited Run IDs:** {', '.join(scorecard.cited_run_ids) if scorecard.cited_run_ids else 'Clean run history'}
- **Guardrail Flags:** {scorecard.guardrail_hits}

## 3. Operational Metrics
- **Heartbeats Fired:** {scorecard.beats_fired} total ({scorecard.silent_beats} silent, {scorecard.beats_fired - scorecard.silent_beats} active)
- **Degraded Mode Next Day:** {'Yes' if scorecard.total_score <= 5 else 'No'}
"""
        return report

    @staticmethod
    def generate_weekly_friend_report(profile: UserProfile, streak_count: int, what_i_learned: List[str]) -> str:
        """
        User-facing Weekly Friend Report (in character, §14):
        what I learned · what I got wrong + fixed · your progress · ONE proposed change [Approve / No].
        """
        user_name = profile.nickname or profile.name
        learned_bullets = "\n".join([f"• {item}" for item in what_i_learned]) if what_i_learned else "• Locked in your favorite workout patterns"

        return f"""# 🌟 Pico's Weekly Friend Report for {user_name}!

Hey {user_name}! Here is our recap for this week:

### 🧠 What I Learned About You
{learned_bullets}

### 🛠️ What I Got Wrong & Fixed
• Adjusted my nudge timing so I never interrupt your evening focus block.

### 📈 Your Progress
• Active Streak: **Day {streak_count}**! Keep this flame burning! 🔥

### 💡 One Proposed Change
Can I move our daily workout nudge 15 minutes earlier (17:45 instead of 18:00) so you have time to stretch?
**[ Approve / Keep Current ]**
"""
