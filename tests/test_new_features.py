"""
Tests for Flagship Innovations (F1 Receipts Timeline, F2 Streak Insurance, F8 Skill Gifting).
From Master Test Report §4 (Top 3 for Ayush).
"""

import pytest
from pico.receipts import ReceiptsTimelineEngine
from pico.streak_insurance import StreakInsuranceEngine
from pico.skill_gifting import SkillGiftingEngine, GiftedSkillPackage
from pico.mcp_host import MCPHost


def test_receipts_timeline_creation_and_correction(tmp_path):
    db_file = str(tmp_path / "test_receipts.db")
    engine = ReceiptsTimelineEngine(db_file)

    # 1. Record an evidence receipt for a claim
    r = engine.record_receipt(
        user_id="ayush_test",
        claim="You completed your push day and hit 75g protein.",
        source_type="memory_fact",
        source_ref="fact:push_workout_done",
        value_recorded={"workout": "push", "protein_g": 75}
    )
    assert r.id.startswith("rcpt_")
    assert r.verified is True

    # 2. Query timeline
    timeline = engine.get_timeline("ayush_test")
    assert len(timeline) == 1
    assert timeline[0].claim == "You completed your push day and hit 75g protein."

    # 3. User correction turns verified=False and stores correction note
    updated = engine.correct_receipt(r.id, "Actually had 90g protein with paneer")
    assert updated is not None
    assert updated.verified is False
    assert updated.user_correction == "Actually had 90g protein with paneer"


def test_streak_insurance_intervention_and_save(tmp_path):
    db_file = str(tmp_path / "test_streak.db")
    engine = StreakInsuranceEngine(db_file)

    # 1. At 21:00 with no activity, streak of 12 is at risk
    is_risk = engine.check_at_risk(current_hour=21, activity_logged_today=False, current_streak=12)
    assert is_risk is True

    # 2. Micro-habit proposal
    proposal = engine.get_insurance_proposal(hobby="gym", current_streak=12)
    assert "squats" in proposal["micro_action"] or "plank" in proposal["micro_action"]
    assert "2-minute" in proposal["proposal_message"]

    # 3. Claim save
    saved_record = engine.claim_save(
        user_id="ayush_test",
        hobby="gym",
        current_streak=12
    )
    assert saved_record.saved_streak_count == 13
    assert "saved via 2-minute micro-habit" in saved_record.notes

    # 4. Check list of saves
    saves = engine.list_saves("ayush_test")
    assert len(saves) == 1
    assert saves[0].hobby == "gym"


def test_skill_gifting_export_verify_and_install():
    # 1. Creator exports a distilled skill
    code = (
        "def execute(inputs: dict) -> dict:\n"
        "    return {'status': 'success', 'gift': True}\n"
    )
    pkg = SkillGiftingEngine.export_skill(
        name="quick_squat_timer",
        creator="Ayush",
        description="2-minute timer for bodyweight workout sets",
        code=code,
        run_count=10,
        success_rate=1.0
    )
    bundle_str = pkg.to_bundle()
    assert isinstance(bundle_str, str)
    assert len(bundle_str) > 50

    # 2. Recipient unpacks and verifies the bundle
    valid, unpacked, msg = SkillGiftingEngine.unpack_gift_bundle(bundle_str)
    assert valid is True
    assert unpacked is not None
    assert unpacked.skill_name == "quick_squat_timer"
    assert unpacked.creator == "Ayush"
    assert unpacked.run_count == 10

    # 3. Consent check: ungated installation MUST fail
    mcp = MCPHost()
    success_ungated, err_ungated = SkillGiftingEngine.install_gift(unpacked, mcp, user_approved=False)
    assert success_ungated is False
    assert "Consent required" in err_ungated

    # 4. Gated installation with explicit recipient consent succeeds
    success_approved, msg_approved = SkillGiftingEngine.install_gift(unpacked, mcp, user_approved=True)
    assert success_approved is True
    assert "Successfully installed gifted skill" in msg_approved
    assert "quick_squat_timer" in mcp.tools
