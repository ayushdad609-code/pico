"""
Tests for Living Artifacts and Indian Rupee Formatting.
From YOUR_FRIEND_FULL_SETUP.pdf (§15 Research, Charts & Artifacts).
"""

from pico.artifacts import format_inr, ArtifactFactory


def test_indian_rupee_formatting():
    assert format_inr(19125123) == "₹1,91,25,123"
    assert format_inr(5000) == "₹5,000"
    assert format_inr(100000) == "₹1,00,000"
    assert format_inr(10000000) == "₹1,00,00,000"


def test_sip_compounding_calculator_exact_match():
    # Settled mathematical formula from §15:
    # monthly SIP at month-start — at ₹5,000/mo, 15%, 26 yrs it yields exactly ₹1,91,25,123
    calc = ArtifactFactory.create_sip_calculator(
        user_id="ayush_01",
        monthly_investment=5000.0,
        expected_cagr=15.0,
        tenure_years=26
    )

    assert calc.summary_header["metric_primary"] == "₹1,91,25,123"
    assert calc.summary_header["metric_secondary"] == "₹15,60,000"  # 5000 * 26 * 12
    assert "boring superpower" in calc.his_line.lower()


def test_his_line_safety_warning_on_absurd_returns():
    # From §15: drag a return slider to 40% and His Line says it has never happened
    # and not to plan on it
    risky_calc = ArtifactFactory.create_sip_calculator(
        user_id="ayush_01",
        monthly_investment=5000.0,
        expected_cagr=45.0,
        tenure_years=10
    )

    assert "never sustainably happened" in risky_calc.his_line
    assert "lottery tickets" in risky_calc.his_line


def test_goal_and_activity_artifacts():
    goal_art = ArtifactFactory.create_goal_tracker("u1", "Launch companion app with 10 testers")
    assert "89 Days Left" in goal_art.summary_header["metric_primary"]

    act_art = ArtifactFactory.create_activity_tracker("u1", streak_days=2, total_reps=20)
    assert act_art.summary_header["metric_primary"] == "Day 2 🔥"
    assert act_art.summary_header["metric_secondary"] == "20 Reps"
