"""
Living Artifacts Engine for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§15 Research, Charts & Artifacts).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional


def format_inr(amount: float) -> str:
    """Formats a number into Indian Rupee digit grouping (e.g. ₹1,91,25,123)."""
    rounded = int(round(amount))
    s = str(abs(rounded))
    if len(s) <= 3:
        formatted = s
    else:
        last3 = s[-3:]
        remaining = s[:-3]
        groups = []
        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.insert(0, remaining)
        formatted = ",".join(groups) + "," + last3

    prefix = "-₹" if rounded < 0 else "₹"
    return prefix + formatted


@dataclass
class Artifact:
    """Living mini-app document structure (§15)."""
    id: str
    user_id: str
    template_type: str  # 'sip_calculator', 'goal_tracker', 'activity_tracker'
    title: str
    mode: str
    summary_header: Dict[str, Any]  # The 2 numbers that matter, huge & live
    controls: Dict[str, Any]        # Sliders / inputs
    visual_data: Dict[str, Any]     # Chart series or progress bars
    his_line: str                   # One in-character sentence regenerated from values
    footer: Dict[str, str]          # source, as_of, assumption_chip
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ArtifactFactory:
    """Builds and recomputes living artifacts."""

    @staticmethod
    def create_sip_calculator(
        user_id: str,
        monthly_investment: float = 5000.0,
        expected_cagr: float = 15.0,
        tenure_years: int = 26
    ) -> Artifact:
        """
        Creates or updates the SIP / Compounding Calculator (MVP ★, §15).
        Formula: Monthly SIP at month-start (Annuity Due).
        At ₹5,000/mo, 15% CAGR, 26 years -> exactly ₹1,91,25,123.
        """
        P = monthly_investment
        r = (expected_cagr / 100.0) / 12.0
        n = tenure_years * 12

        # Annuity Due formula
        if r > 0:
            fv = P * (((1 + r)**n - 1) / r) * (1 + r)
        else:
            fv = P * n

        total_invested = P * n
        estimated_returns = max(0.0, fv - total_invested)

        # Generate "His Line" dynamically based on parameters (§15)
        if expected_cagr > 40.0:
            his_line = "Whoa there, chief! 🛑 A return over 40% has never sustainably happened in modern history. Let's not plan your life on lottery tickets!"
        elif expected_cagr > 22.0:
            his_line = "That's super spicy! Remember that higher returns usually come with wild rollercoaster stomach drops."
        elif tenure_years >= 20:
            his_line = f"Disciplined patience is your boring superpower! Sticking to {format_inr(P)}/mo turns steady consistency into {format_inr(fv)}."
        else:
            his_line = f"Every single month you invest {format_inr(P)}, you buy a tiny slice of your future freedom."

        return Artifact(
            id=f"art_sip_{user_id}",
            user_id=user_id,
            template_type="sip_calculator",
            title="SIP Compounding Calculator",
            mode="trading",
            summary_header={
                "metric_primary": format_inr(fv),
                "label_primary": "Expected Wealth (Total Value)",
                "metric_secondary": format_inr(total_invested),
                "label_secondary": "Total You Invest"
            },
            controls={
                "monthly_sip": P,
                "expected_return_pct": expected_cagr,
                "time_period_years": tenure_years
            },
            visual_data={
                "invested_amount": total_invested,
                "est_returns": estimated_returns,
                "total_value": fv
            },
            his_line=his_line,
            footer={
                "source": "Mathematical Compound Growth (Month-start Annuity Due)",
                "as_of": datetime.now(timezone.utc).strftime("%b %Y"),
                "assumption_chip": f"Assumes {expected_cagr}% CAGR. Mutual fund investments are subject to market risks."
            }
        )

    @staticmethod
    def create_goal_tracker(user_id: str, goal_text: str, days_total: int = 90) -> Artifact:
        """
        Auto-built 90-Day Goal Tracker artifact (§15).
        """
        days_passed = 1
        days_remaining = days_total - days_passed
        progress_pct = round((days_passed / days_total) * 100, 1)

        return Artifact(
            id=f"art_goal_{user_id}",
            user_id=user_id,
            template_type="goal_tracker",
            title="90-Day Living Goal Tracker",
            mode="chill",
            summary_header={
                "metric_primary": f"{days_remaining} Days Left",
                "label_primary": "Countdown to 90 Days",
                "metric_secondary": f"{progress_pct}%",
                "label_secondary": "Sprint Completion"
            },
            controls={
                "days_total": days_total,
                "goal_text": goal_text
            },
            visual_data={
                "days_passed": days_passed,
                "days_remaining": days_remaining,
                "progress_percentage": progress_pct
            },
            his_line=f"Day {days_passed} of 90! Every big milestone is just a bundle of tiny daily wins.",
            footer={
                "source": "Personal Onboarding Commitment",
                "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "assumption_chip": "Updated automatically on weekly Sunday check-in."
            }
        )

    @staticmethod
    def create_activity_tracker(user_id: str, streak_days: int = 1, total_reps: int = 10) -> Artifact:
        """
        Activity Progress Tracker artifact (§15).
        """
        return Artifact(
            id=f"art_activity_{user_id}",
            user_id=user_id,
            template_type="activity_tracker",
            title="Fitness & Streak Tracker",
            mode="gym",
            summary_header={
                "metric_primary": f"Day {streak_days} 🔥",
                "label_primary": "Current Workout Streak",
                "metric_secondary": f"{total_reps} Reps",
                "label_secondary": "Total Reps Logged"
            },
            controls={
                "streak": streak_days,
                "total_reps": total_reps
            },
            visual_data={
                "streak_heatmap": [1] * min(streak_days, 7),
                "recent_sessions": [{"date": "Today", "activity": "Pushups", "reps": total_reps}]
            },
            his_line="The flame is lit! Scheduled rest days won't break it, so show up with honest effort.",
            footer={
                "source": "Pico Gym Ledger",
                "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "assumption_chip": "Form verdicts need video; single still = observation only."
            }
        )
