"""
Fast-Path Onboarding Engine for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§7 Onboarding — 5 pages to a living Pico).
"""

from typing import List, Optional, Dict, Any
from .models import UserProfile


# The 20 "Relates With You" launch categories (§7)
LAUNCH_CATEGORIES = [
    "Gym & Fitness",
    "Crypto Trading",
    "Stock Market",
    "Study & Exams",
    "Business & Startups",
    "Coding & Tech",
    "Content Creation",
    "E-commerce",
    "Gaming",
    "Sports",
    "Food & Cooking",
    "Travel",
    "Music",
    "Movies/Anime/Manga",
    "Money & Side Hustles",
    "Health/Sleep/Mind",
    "Relationships",
    "Learning a Language",
    "Reading & Writing",
    "Just want a friend"
]


class OnboardingFlow:
    """Manages the 5-page fast-path onboarding flow into a living Pico."""

    @staticmethod
    def create_fast_path_profile(
        user_id: str,
        name: str,
        nickname: Optional[str] = None,
        age: int = 22,
        languages: Optional[List[str]] = None,
        selected_categories: Optional[List[str]] = None,
        job: Optional[str] = None,
        goal_90d: Optional[str] = None,
        wake_time: str = "07:00",
        sleep_time: str = "23:00",
        funny_angry_opt_in: bool = False
    ) -> UserProfile:
        """
        Creates a completed fast-path UserProfile with default Chill Mode ready to run.
        """
        langs = languages or ["English"]
        cats = selected_categories or ["Just want a friend"]
        is_minor = (age < 18)

        # Enforce Under-18 Safe Mode (§17): no funny-angry, strict guards
        if is_minor:
            funny_angry_opt_in = False

        # Primary hobby is the first selected category
        primary_hobby = cats[0].lower().replace(" & ", "_").replace(" ", "_") if cats else "chill"

        profile = UserProfile(
            user_id=user_id,
            name=name.strip(),
            nickname=nickname.strip() if nickname else name.strip(),
            age=age,
            is_minor=is_minor,
            languages=langs,
            primary_hobby=primary_hobby,
            selected_hobbies=cats,
            job=job,
            goal_90d=goal_90d,
            wake_time=wake_time,
            sleep_time=sleep_time,
            funny_angry_opt_in=funny_angry_opt_in
        )

        return profile

    @staticmethod
    def validate_90d_goal(goal_text: str) -> bool:
        """
        Validates founder's rule (§7): minimum 20 words for the 90-day goal.
        """
        if not goal_text:
            return False
        words = goal_text.strip().split()
        return len(words) >= 20
