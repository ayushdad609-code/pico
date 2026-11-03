"""
Routine Graph — The Daily Spine of Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§1 Routine Pillar, §6 Day Path, §9 Memory System).
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Optional, Dict, Any
from .models import UserProfile


@dataclass
class RoutineNode:
    """A node along today's routine path."""
    id: str
    name: str
    start_time: str  # "HH:MM" 24h format
    end_time: str    # "HH:MM" 24h format
    mode: str = "chill"
    days: List[str] = field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    is_essential: bool = True
    completed_today: bool = False

    def to_time_range(self) -> tuple[time, time]:
        sh, sm = map(int, self.start_time.split(":"))
        eh, em = map(int, self.end_time.split(":"))
        return time(sh, sm), time(eh, em)


class RoutineGraph:
    """Manages the user's daily spine and day-path nodes."""
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.nodes: List[RoutineNode] = []

    def add_node(self, node: RoutineNode):
        self.nodes.append(node)
        self.nodes.sort(key=lambda n: n.start_time)

    @classmethod
    def seed_from_profile(cls, profile: UserProfile) -> "RoutineGraph":
        """
        Creates the default routine spine based on onboarding wake/sleep times.
        Spine: Wake -> Morning Focus -> Work/Job Block -> Hobby Session -> Evening Review -> Sleep
        """
        graph = cls(profile.user_id)
        wake = profile.wake_time or "07:00"
        sleep = profile.sleep_time or "23:00"

        # 1. Wake & Morning Brief
        graph.add_node(RoutineNode(
            id="node_wake",
            name="Morning Rise & Brief",
            start_time=wake,
            end_time="08:30",
            mode="chill"
        ))

        # 2. Work / Study / Deep Block
        graph.add_node(RoutineNode(
            id="node_work_block",
            name="Core Focus / Work Block",
            start_time="09:30",
            end_time="17:30",
            mode=profile.primary_hobby or "chill"
        ))

        # 3. Hobby / Workout Session
        graph.add_node(RoutineNode(
            id="node_hobby",
            name=f"{profile.primary_hobby.replace('_', ' ').title() if profile.primary_hobby else 'Activity'} Session",
            start_time="18:30",
            end_time="19:45",
            mode=profile.primary_hobby or "gym"
        ))

        # 4. Evening Review (Settled at 21:30 in §8)
        graph.add_node(RoutineNode(
            id="node_evening_review",
            name="Evening Review & Day Close",
            start_time="21:30",
            end_time="22:00",
            mode="chill"
        ))

        # 5. Sleep / Quiet Hours
        graph.add_node(RoutineNode(
            id="node_sleep",
            name="Wind-down & Rest",
            start_time=sleep,
            end_time="23:59",
            mode="chill"
        ))

        return graph

    def get_current_node(self, current_time_str: Optional[str] = None) -> Optional[RoutineNode]:
        """Returns the currently active routine node."""
        if current_time_str:
            ch, cm = map(int, current_time_str.split(":"))
            now_t = time(ch, cm)
        else:
            now_t = datetime.now().time()

        for node in self.nodes:
            st, et = node.to_time_range()
            if st <= now_t <= et:
                return node
        return None

    def get_upcoming_node(self, current_time_str: Optional[str] = None, window_minutes: int = 60) -> Optional[tuple[RoutineNode, int]]:
        """
        Returns (node, minutes_until) for a node starting within window_minutes.
        Used by the 30-min heartbeat check #1.
        """
        if current_time_str:
            ch, cm = map(int, current_time_str.split(":"))
        else:
            now = datetime.now()
            ch, cm = now.hour, now.minute

        now_minutes = ch * 60 + cm

        for node in self.nodes:
            sh, sm = map(int, node.start_time.split(":"))
            start_minutes = sh * 60 + sm
            delta = start_minutes - now_minutes
            if 0 < delta <= window_minutes:
                return node, delta
        return None

    def render_day_path(self, current_time_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Renders the Duolingo-style day path (wake -> work -> session -> evening)
        with the current active node flagged for pulsing UI.
        """
        current = self.get_current_node(current_time_str)
        path = []
        for node in self.nodes:
            is_active = (current and current.id == node.id)
            path.append({
                "id": node.id,
                "name": node.name,
                "time": f"{node.start_time} - {node.end_time}",
                "mode": node.mode,
                "is_active": is_active,
                "status": "in_progress" if is_active else ("completed" if node.completed_today else "upcoming")
            })
        return path
