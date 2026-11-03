"""
24/7 Heartbeat Daemon & Watcher Worker for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§8 Scheduled Work, §13.3 Heartbeat, §19.5 Alerts).
"""

import time
import signal
import sys
from datetime import datetime, timezone
from typing import Optional
from .models import UserProfile
from .onboarding import OnboardingFlow
from .memory import MemoryStore
from .routine import RoutineGraph
from .scheduled import ScheduledWorkRegistry
from .heartbeat import HeartbeatRunner, HeartbeatOutcome
from .watchers import PriceWatcher, PriceWatcherEngine


class HeartbeatDaemon:
    def __init__(
        self,
        db_path: str = "/data/data/com.termux/files/home/pico/pico_chat.db",
        tick_interval_seconds: int = 1800  # Default 30 minutes (1800s)
    ):
        self.db_path = db_path
        self.tick_interval = tick_interval_seconds
        self.running = True

        self.memory = MemoryStore(db_path)
        self.profile = OnboardingFlow.create_fast_path_profile(
            user_id="ayush_01",
            name="Ayush",
            nickname="Ayush",
            age=24,
            languages=["English", "Hinglish"],
            selected_categories=["Coding & Tech", "Gym & Fitness"]
        )
        self.routine = RoutineGraph.seed_from_profile(self.profile)
        self.scheduled = ScheduledWorkRegistry.install_defaults(self.profile)
        self.heartbeat = HeartbeatRunner(self.profile, self.routine, self.scheduled)
        self.watchers = PriceWatcherEngine()

        # Arm default Bitcoin price watcher
        self.watchers.add_watcher(PriceWatcher(
            id="daemon_btc_watch",
            user_id=self.profile.user_id,
            symbol="BTCUSDT",
            target_level=65000.0,
            direction="below"
        ))

        # Register OS signal handlers for clean exit
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _handle_exit(self, signum, frame):
        print("\n[Pico Daemon] Received shutdown signal. Closing clean...")
        self.running = False

    def run_one_tick(self) -> dict:
        """Runs a single evaluation tick across watchers and heartbeat."""
        now = datetime.now()
        now_str = now.strftime("%H:%M")

        # 1. Evaluate Market Watchers (P0 Priority)
        alerts = self.watchers.evaluate_watchers()
        fired_alerts = []
        for a in alerts:
            print(f"\n🚨 [P0 WATCHER FIRED]: {a.push_notification}")
            print(f"📱 [IN-APP]: {a.in_app_card['headline']}")
            fired_alerts.append(a.push_notification)

        # 2. Fire 30-min Heartbeat (P2 Proactive)
        beat = self.heartbeat.fire_beat(now_str)
        print(f"💓 [Heartbeat #{beat.beat_number} at {now_str}]: Outcome={beat.outcome.value} ({beat.reason})")

        return {
            "time": now_str,
            "beat_number": beat.beat_number,
            "outcome": beat.outcome.value,
            "reason": beat.reason,
            "alerts": fired_alerts
        }

    def start_loop(self, max_ticks: Optional[int] = None):
        """Starts the persistent background daemon loop."""
        print(f"🌟 [Pico Daemon Started] Tick interval: {self.tick_interval}s. Watching over {self.profile.name}'s day.")
        tick_count = 0
        while self.running:
            self.run_one_tick()
            tick_count += 1
            if max_ticks and tick_count >= max_ticks:
                break

            # Sleep in 1-second chunks to respond quickly to termination signals
            for _ in range(self.tick_interval):
                if not self.running:
                    break
                time.sleep(1)

        print("[Pico Daemon] Gracefully stopped.")


if __name__ == "__main__":
    interval = 1800
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        interval = int(sys.argv[1])
    daemon = HeartbeatDaemon(tick_interval_seconds=interval)
    daemon.start_loop()
