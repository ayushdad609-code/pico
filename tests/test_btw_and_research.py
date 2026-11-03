"""
Tests for BTW Engine and Research Engine.
From YOUR_FRIEND_FULL_SETUP.pdf (§11 BTW Engine, §15 Research Briefs).
"""

from pico.models import PersonaPacket, EmotionAssessment, ReactionPlan, EmotionSensitivity, PicoEmotion
from pico.btw import BTWEngine, MemoryGap
from pico.research import ResearchEngine, ClaimTag


def test_btw_engine_ask_gate_and_veto():
    engine = BTWEngine()
    user_id = "u_btw"
    engine.seed_starter_bank_for_hobby(user_id, "gym")

    # Packet during tender/sad moments -> Ask Gate MUST VETO
    sad_packet = PersonaPacket(
        mode="gym",
        emotion_assessment=EmotionAssessment(sensitivity=EmotionSensitivity.TENDER, primary="sad"),
        reaction_plan=ReactionPlan(do_not_list=["NO BTW asks"])
    )
    passed, gap = engine.evaluate_ask_gate(sad_packet, current_topic="gym")
    assert passed is False
    assert gap is None

    # Normal calm packet with value delivered -> Ask Gate passes
    calm_packet = PersonaPacket(
        mode="gym",
        emotion_assessment=EmotionAssessment(sensitivity=EmotionSensitivity.NORMAL, primary="neutral"),
        reaction_plan=ReactionPlan()
    )
    passed2, gap2 = engine.evaluate_ask_gate(calm_packet, current_topic="gym", value_delivered=True)
    assert passed2 is True
    assert gap2 is not None
    assert "protein" in gap2.question_template or "injury" in gap2.question_template

    # Gate prevents asking twice in a row (none in last 3 outputs rule)
    passed3, gap3 = engine.evaluate_ask_gate(calm_packet, current_topic="gym", value_delivered=True)
    assert passed3 is False


def test_btw_capture_answer():
    engine = BTWEngine()
    user_id = "u_ans"
    engine.seed_starter_bank_for_hobby(user_id, "gym")

    calm_packet = PersonaPacket(mode="gym")
    passed, gap = engine.evaluate_ask_gate(calm_packet, current_topic="gym", value_delivered=True)
    assert passed is True

    # User answers
    fact = engine.capture_answer("I drink whey protein twice a day", user_id)
    assert fact is not None
    assert fact.key == "protein_style"
    assert "whey protein" in fact.value
    assert fact.status.value == "committed"


def test_research_engine_claim_tags():
    brief = ResearchEngine.generate_research_brief("u1", "Rive Vector Animation Performance")

    assert len(brief.claims) >= 3
    tags = [c.tag for c in brief.claims]
    assert ClaimTag.VERIFIED in tags
    assert ClaimTag.REPORTED in tags
    assert ClaimTag.UNVERIFIED in tags

    assert "Rive" in brief.claims[0].statement
    assert "Duolingo" in brief.claims[0].source
