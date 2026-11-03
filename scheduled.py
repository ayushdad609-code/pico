"""
Scheduled Work Engine for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§8 Scheduled Work — trust rule).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from .models import UserProfile


@dataclass
class ScheduledJob:
    """A scheduled job visible in the Scheduled tab (§8)."""
    id: str
    name: str
    schedule_display: str  # e.g., "At wake time (07:00)", "Daily at 21:30"
    trigger_time: str      # "HH:MM"
    enabled: bool = True
    last_run_result: Optional[str] = None
    last_run_time: Optional[str] = None
    next_run_time: Optional[str] = None
    consecutive_failures: int = 0

    def record_run(self, success: bool, message: str = "Completed successfully"):
        self.last_run_time = datetime.now(timezone.utc).isoformat()
        if success:
            self.last_run_result = f"Success: {message}"
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            self.last_run_result = f"Failed ({self.consecutive_failures}x): {message}"


class ScheduledWorkRegistry:
    """Manages scheduled jobs installed at onboarding (§8)."""
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.jobs: Dict[str, ScheduledJob] = {}

    @classmethod
    def install_defaults(cls, profile: UserProfile) -> "ScheduledWorkRegistry":
        """Installs the default jobs per §8."""
        reg = cls(profile.user_id)
        wake = profile.wake_time or "07:00"

        # 1. Morning Brief (at wake time)
        reg.register(ScheduledJob(
            id="morning_brief",
            name="Morning Brief",
            schedule_display=f"Daily at wake time ({wake})",
            trigger_time=wake
        ))

        # 2. Hobby Nudge (per Mode schedule, e.g. 18:00)
        reg.register(ScheduledJob(
            id="hobby_nudge",
            name="Hobby Nudge",
            schedule_display="Daily at 18:00",
            trigger_time="18:00"
        ))

        # 3. Evening Review (21:30)
        reg.register(ScheduledJob(
            id="evening_review",
            name="Evening Review",
            schedule_display="Daily at 21:30",
            trigger_time="21:30"
        ))

        # 4. Streak-Save Warning (20:00)
        reg.register(ScheduledJob(
            id="streak_warning",
            name="Streak-Save Warning",
            schedule_display="Daily at 20:00 if inactive",
            trigger_time="20:00"
        ))

        # 5. Nightly Self-Check (system, view-only, 03:00)
        reg.register(ScheduledJob(
            id="nightly_self_check",
            name="Nightly Self-Check & Scorecard",
            schedule_display="Nightly at 03:00",
            trigger_time="03:00"
        ))

        return reg

    def register(self, job: ScheduledJob):
        self.jobs[job.id] = job

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Returns job list for display in the Scheduled Work tab."""
        return [
            {
                "id": j.id,
                "name": j.name,
                "schedule": j.schedule_display,
                "enabled": j.enabled,
                "last_run": j.last_run_result or "Never run",
                "failures": j.consecutive_failures
            }
            for j in self.jobs.values()
        ]
