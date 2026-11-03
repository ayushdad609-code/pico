"""
Tests for Pico Onboarding Flow.
"""

from pico.onboarding import OnboardingFlow, LAUNCH_CATEGORIES


def test_fast_path_creation():
    profile = OnboardingFlow.create_fast_path_profile(
        user_id="user_123",
        name="Ayush",
        nickname="Ayu",
        age=24,
        languages=["English", "Hindi"],
        selected_categories=["Gym & Fitness"]
    )

    assert profile.name == "Ayush"
    assert profile.nickname == "Ayu"
    assert profile.age == 24
    assert profile.is_minor is False
    assert profile.primary_hobby == "gym_fitness"
    assert profile.languages == ["English", "Hindi"]


def test_under_18_minor_protection():
    # If age < 18, safe mode is engaged and funny-angry opt-in is forced False
    profile = OnboardingFlow.create_fast_path_profile(
        user_id="minor_001",
        name="Alex",
        age=16,
        funny_angry_opt_in=True
    )

    assert profile.is_minor is True
    assert profile.funny_angry_opt_in is False


def test_90_day_goal_minimum_20_words():
    # Less than 20 words
    short_goal = "I want to get fit and learn to code in 3 months."
    assert OnboardingFlow.validate_90d_goal(short_goal) is False

    # 20+ words
    valid_goal = (
        "I want to build a consistent 4-day gym routine, increase my bench press to 80kg, "
        "and complete building my new software companion project before December ends."
    )
    words = valid_goal.strip().split()
    assert len(words) >= 20
    assert OnboardingFlow.validate_90d_goal(valid_goal) is True


def test_20_launch_categories():
    assert len(LAUNCH_CATEGORIES) == 20
    assert "Gym & Fitness" in LAUNCH_CATEGORIES
    assert "Crypto Trading" in LAUNCH_CATEGORIES
    assert "Just want a friend" in LAUNCH_CATEGORIES
