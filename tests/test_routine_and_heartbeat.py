"""
Tests for Routine Graph, Briefs, Heartbeat, and Self-Analysis reports.
"""

from pico.models import UserProfile
from pico.onboarding import OnboardingFlow
from pico.routine import RoutineGraph, RoutineNode
from pico.briefs import BriefGenerator
from pico.scheduled import ScheduledWorkRegistry
from pico.heartbeat import HeartbeatRunner, HeartbeatOutcome
from pico.reports import SelfAnalysisEngine, DailyScorecard


def test_routine_graph_seed():
    profile = OnboardingFlow.create_fast_path_profile("u1", "Ayush", wake_time="06:30", sleep_time="23:30")
    graph = RoutineGraph.seed_from_profile(profile)

    assert len(graph.nodes) >= 5
    node_ids = [n.id for n in graph.nodes]
    assert "node_wake" in node_ids
    assert "node_work_block" in node_ids
    assert "node_evening_review" in node_ids

    # Wake start time matches profile
    wake_node = next(n for n in graph.nodes if n.id == "node_wake")
    assert wake_node.start_time == "06:30"


def test_routine_current_and_upcoming_node():
    profile = OnboardingFlow.create_fast_path_profile("u1", "Ayush", wake_time="07:00")
    graph = RoutineGraph.seed_from_profile(profile)

    # Active node at 07:30
    curr = graph.get_current_node("07:30")
    assert curr is not None
    assert curr.id == "node_wake"

    # Upcoming node at 06:15 (wake is at 07:00, which is 45 mins away)
    upcoming = graph.get_upcoming_node("06:15", window_minutes=60)
    assert upcoming is not None
    node, minutes = upcoming
    assert node.id == "node_wake"
    assert minutes == 45


def test_day_path_rendering():
    profile = OnboardingFlow.create_fast_path_profile("u1", "Ayush")
    graph = RoutineGraph.seed_from_profile(profile)

    path = graph.render_day_path("10:00")
    assert len(path) >= 5
    work_node = next(p for p in path if p["id"] == "node_work_block")
    assert work_node["is_active"] is True
    assert work_node["status"] == "in_progress"


def test_brief_generators_word_caps():
    profile = OnboardingFlow.create_fast_path_profile(
        "u1",
        "Ayush",
        goal_90d="Complete building the mobile companion prototype with Rive animation and fast SQLite memory"
    )
    graph = RoutineGraph.seed_from_profile(profile)

    # Morning brief <= 120 words
    morning = BriefGenerator.generate_morning_brief(profile, graph)
    assert len(morning.split()) <= 120
    assert "Ayush" in morning
    assert "ONE thing" in morning

    # Evening review <= 150 words
    evening = BriefGenerator.generate_evening_review(profile, streak_count=3, completed_tasks=["10 Pushups", "Cleaned code"])
    assert len(evening.split()) <= 150
    assert "Day 3" in evening
    assert "10 Pushups" in evening


def test_heartbeat_outcomes():
    profile = OnboardingFlow.create_fast_path_profile(
        "u1",
        "Ayush",
        wake_time="07:00",
        sleep_time="23:00"
    )
    profile.quiet_hours_start = "22:00"
    profile.quiet_hours_end = "07:00"

    graph = RoutineGraph.seed_from_profile(profile)
    reg = ScheduledWorkRegistry.install_defaults(profile)
    runner = HeartbeatRunner(profile, graph, reg)

    # 1. Normal middle of day beat -> SILENT
    b1 = runner.fire_beat("14:00", streak_done_today=True)
    assert b1.outcome == HeartbeatOutcome.SILENT

    # 2. Scheduled Job due at 21:30 (Evening review) outside quiet hours -> SPEAK
    b2 = runner.fire_beat("21:30", streak_done_today=True)
    assert b2.outcome == HeartbeatOutcome.SPEAK
    assert "Evening Review" in b2.reason

    # 3. Scheduled job due during quiet hours (e.g. 03:00) -> converts to PREPARE
    b3 = runner.fire_beat("03:00")
    assert b3.outcome == HeartbeatOutcome.PREPARE
    assert b3.was_quiet_hours is True

    # 4. Streak-risk window (20:30, no streak done today) -> SPEAK
    b4 = runner.fire_beat("20:30", streak_done_today=False)
    assert b4.outcome == HeartbeatOutcome.SPEAK
    assert "Streak-risk" in b4.reason

    # 5. Broken promise -> ESCALATE
    b5 = runner.fire_beat("15:00", broken_promise_event={"description": "Flight DEL->BLR cancelled"})
    assert b5.outcome == HeartbeatOutcome.ESCALATE


def test_scorecard_and_degraded_mode():
    profile = OnboardingFlow.create_fast_path_profile("u1", "Ayush")

    # Clean scorecard
    clean_card = DailyScorecard(user_id="u1", date="2026-11-03")
    assert clean_card.total_score == 10
    report = SelfAnalysisEngine.generate_nightly_report(clean_card, profile)
    assert "HEALTHY" in report

    # Failed scorecard (guardrail flag caps at 5)
    failing_card = DailyScorecard(user_id="u1", date="2026-11-03", guardrail_hits=1)
    assert failing_card.total_score <= 5
    fail_report = SelfAnalysisEngine.generate_nightly_report(failing_card, profile)
    assert "DEGRADED MODE" in fail_report
