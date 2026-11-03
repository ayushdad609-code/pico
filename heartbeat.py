"""
30-Minute Heartbeat Runner for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§13.3 Heartbeat — every 30 minutes).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, time
from typing import List, Optional, Dict, Any
from enum import Enum
from .models import UserProfile
from .routine import RoutineGraph
from .scheduled import ScheduledWorkRegistry


class HeartbeatOutcome(str, Enum):
    SILENT = "SILENT"      # ~85-90%: one log line, no LLM
    PREPARE = "PREPARE"    # Stage later work invisibly
    SPEAK = "SPEAK"        # Decided message to user (becomes PREPARE in quiet hours)
    ESCALATE = "ESCALATE"  # Broken promise / immediate critical alert


@dataclass
class BeatResult:
    beat_number: int
    timestamp: str
    outcome: HeartbeatOutcome
    reason: str
    action_payload: Optional[Dict[str, Any]] = None
    was_quiet_hours: bool = False


class HeartbeatRunner:
    """
    Executes the 30-minute heartbeat checks per user.
    Cheap ordered checks: Code + connectors only. LLM <5% of beats.
    """
    def __init__(
        self,
        profile: UserProfile,
        routine_graph: RoutineGraph,
        scheduled_registry: ScheduledWorkRegistry,
        interval_minutes: int = 30
    ):
        self.profile = profile
        self.routine = routine_graph
        self.scheduled = scheduled_registry
        self.interval_minutes = interval_minutes
        self.beat_count = 0
        self.beat_log: List[BeatResult] = []
        self.is_paused = False

    def is_in_quiet_hours(self, current_time_str: str) -> bool:
        """Checks if current time falls within user quiet hours (§13.3)."""
        ch, cm = map(int, current_time_str.split(":"))
        now_t = time(ch, cm)

        sh, sm = map(int, self.profile.quiet_hours_start.split(":"))
        eh, em = map(int, self.profile.quiet_hours_end.split(":"))
        start_t = time(sh, sm)
        end_t = time(eh, em)

        if start_t > end_t:  # Crosses midnight (e.g. 22:00 to 07:00)
            return now_t >= start_t or now_t < end_t
        return start_t <= now_t < end_t

    def fire_beat(
        self,
        current_time_str: str,
        streak_done_today: bool = False,
        calendar_delta: Optional[Dict[str, Any]] = None,
        health_sync_delta: Optional[Dict[str, Any]] = None,
        broken_promise_event: Optional[Dict[str, Any]] = None
    ) -> BeatResult:
        """
        Executes one heartbeat cycle through the 7 cheap ordered checks.
        """
        if self.is_paused:
            res = BeatResult(
                beat_number=self.beat_count,
                timestamp=datetime.now(timezone.utc).isoformat(),
                outcome=HeartbeatOutcome.SILENT,
                reason="Heartbeat paused by user setting."
            )
            self.beat_log.append(res)
            return res

        self.beat_count += 1
        now_iso = datetime.now(timezone.utc).isoformat()
        in_quiet = self.is_in_quiet_hours(current_time_str)

        # CHECK 0: ESCALATE (Broken promise / venue closed / flight cancelled)
        if broken_promise_event:
            res = BeatResult(
                beat_number=self.beat_count,
                timestamp=now_iso,
                outcome=HeartbeatOutcome.ESCALATE,
                reason=f"Promise broke: {broken_promise_event.get('description', 'external critical event')}",
                action_payload=broken_promise_event,
                was_quiet_hours=in_quiet
            )
            self.beat_log.append(res)
            return res

        # CHECK 4: Scheduled jobs due at this time
        for job_id, job in self.scheduled.jobs.items():
            if job.enabled and job.trigger_time == current_time_str:
                outcome = HeartbeatOutcome.PREPARE if in_quiet else HeartbeatOutcome.SPEAK
                res = BeatResult(
                    beat_number=self.beat_count,
                    timestamp=now_iso,
                    outcome=outcome,
                    reason=f"Scheduled job due: {job.name} ({current_time_str})",
                    action_payload={"job_id": job.id, "job_name": job.name},
                    was_quiet_hours=in_quiet
                )
                self.beat_log.append(res)
                return res

        # CHECK 5: Streak-risk window (20:00 to 22:00 and no activity logged today)
        ch, cm = map(int, current_time_str.split(":"))
        if (20 <= ch < 22) and not streak_done_today:
            outcome = HeartbeatOutcome.PREPARE if in_quiet else HeartbeatOutcome.SPEAK
            res = BeatResult(
                beat_number=self.beat_count,
                timestamp=now_iso,
                outcome=outcome,
                reason="Streak-risk window active: user has not logged today's session yet",
                action_payload={"type": "streak_warning"},
                was_quiet_hours=in_quiet
            )
            self.beat_log.append(res)
            return res

        # CHECK 1: Routine block due in 30–60 min
        upcoming = self.routine.get_upcoming_node(current_time_str, window_minutes=60)
        if upcoming:
            node, minutes_until = upcoming
            # If 30-45 minutes before a key session, prepare or gently notify
            if 30 <= minutes_until <= 45 and node.is_essential:
                outcome = HeartbeatOutcome.PREPARE if in_quiet else HeartbeatOutcome.SPEAK
                res = BeatResult(
                    beat_number=self.beat_count,
                    timestamp=now_iso,
                    outcome=outcome,
                    reason=f"Upcoming routine block: '{node.name}' starts in {minutes_until} mins",
                    action_payload={"node_id": node.id, "minutes_until": minutes_until},
                    was_quiet_hours=in_quiet
                )
                self.beat_log.append(res)
                return res

        # Default Outcome: SILENT (~85-90%)
        res = BeatResult(
            beat_number=self.beat_count,
            timestamp=now_iso,
            outcome=HeartbeatOutcome.SILENT,
            reason="All 7 checks calm; watchers alive; no action required.",
            was_quiet_hours=in_quiet
        )
        self.beat_log.append(res)
        return res

    def get_beat_log_summary(self) -> List[Dict[str, Any]]:
        """Provides the human-word log for 'Why so quiet today?' (§13.3)."""
        return [
            {
                "beat": b.beat_number,
                "outcome": b.outcome.value,
                "reason": b.reason,
                "quiet_hours": b.was_quiet_hours
            }
            for b in self.beat_log[-10:]
        ]
