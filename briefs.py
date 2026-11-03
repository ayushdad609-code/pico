"""
Morning Brief and Evening Review Generators for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§8 App Structure, §18.5 Brief Formats).
"""

from typing import Optional, List, Dict, Any
from .models import UserProfile, MemoryPack
from .routine import RoutineGraph


class BriefGenerator:
    """Generates strictly structured Morning Briefs and Evening Reviews."""

    @staticmethod
    def generate_morning_brief(
        profile: UserProfile,
        routine_graph: RoutineGraph,
        memory_pack: Optional[MemoryPack] = None,
        watcher_updates: Optional[List[str]] = None
    ) -> str:
        """
        Morning Brief format (§18.5):
        Greeting -> Today's shape -> The ONE thing that matters most -> Overnight watcher news -> Small close.
        Hard cap: <= 120 words.
        """
        user_name = profile.nickname or profile.name

        # 1. Greeting
        greeting = f"Good morning, {user_name}! ☀️"

        # 2. Today's shape
        upcoming = [n.name for n in routine_graph.nodes if n.id not in ["node_wake", "node_sleep"]][:2]
        shape_text = f"Today's rhythm has {', and '.join(upcoming)} on the map." if upcoming else "Today is wide open for focused progress."

        # 3. The ONE thing that matters most
        one_thing = (
            f"The ONE thing today: make a tangible dent in '{profile.goal_90d}'."
            if profile.goal_90d
            else "The ONE thing today: show up for your planned session and keep our streak alive."
        )

        # 4. Watcher news
        if watcher_updates:
            watcher_news = f"Overnight watchers: {'; '.join(watcher_updates)}."
        else:
            watcher_news = "Overnight watchers are calm — no alarms tripped."

        # 5. Small close
        close = "I've got my notebook open and your back all day. Let's make it a great one!"

        brief = f"{greeting} {shape_text} {one_thing} {watcher_news} {close}"

        # Word count safety check (morning <= 120 words)
        words = brief.split()
        if len(words) > 120:
            brief = " ".join(words[:115]) + " Let's go!"

        return brief

    @staticmethod
    def generate_evening_review(
        profile: UserProfile,
        streak_count: int = 1,
        completed_tasks: Optional[List[str]] = None,
        missed_tasks: Optional[List[str]] = None
    ) -> str:
        """
        Evening Review format (§8 Evening Review 21:30, §18.5):
        Greeting -> What was finished vs planned -> Streak celebration/check -> Wind-down close.
        Hard cap: <= 150 words.
        """
        user_name = profile.nickname or profile.name

        greeting = f"Evening check-in, {user_name}! 🌙"

        if completed_tasks:
            recap = f"You showed up and finished: {', '.join(completed_tasks)}."
        else:
            recap = "We had a quiet day on the task board."

        streak_text = f"Our streak is officially at Day {streak_count}! Every single day adds another layer of discipline."

        wind_down = "Rest is where all your gains and learning actually lock in. Wrap things up, unwind, and sleep deep tonight. Proud of you!"

        review = f"{greeting} {recap} {streak_text} {wind_down}"

        # Word count safety check (evening <= 150 words)
        words = review.split()
        if len(words) > 150:
            review = " ".join(words[:145]) + " Goodnight!"

        return review
