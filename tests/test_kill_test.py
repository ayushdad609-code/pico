"""
Pytest unit tests for Pico Multi-User 7-Day Kill-Test.
"""

from pico.kill_test_runner import KillTestRunner


def test_kill_test_runner_all_gates_pass():
    runner = KillTestRunner(db_path=":memory:")
    result = runner.run_simulation()

    assert result.passed_all_gates is True
    assert result.total_testers == 10
    assert result.total_simulated_days == 7
    assert result.day7_retained_users >= 5
    assert result.retention_rate_pct >= 50.0
    assert result.tokens_under_budget is True
    assert result.guardrails_blocked == result.total_guardrail_probes
    assert result.quiet_hour_violations == 0
    assert result.average_scorecard >= 6.0
