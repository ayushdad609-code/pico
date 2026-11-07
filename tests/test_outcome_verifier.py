"""Tests for Outcome Verifier, AI Identity Disclosure, and Robot Inquiries (Doc 33 Stage D & Doc 35 §6)."""

import pytest
from telephony.briefing import FactsPacket, CalleeInfo, AuthorityLevel
from telephony.call_session import CallSession, CallStatus
from telephony.outcome_verifier import (
    OutcomeVerifier,
    VerificationStatus,
    verify_booking_outcome,
    handle_robot_inquiry
)

def test_robot_inquiry_detection_and_honest_disclosure():
    # Various ways callees ask if the caller is a robot/AI
    queries = [
        "Are you a robot?",
        "Is this an AI or a real person?",
        "Kya aap machine bol rahe ho?",
        "Are you an automated bot?",
        "Am I speaking to a human?",
        "Who is this, a computer?",
    ]
    for q in queries:
        ans = handle_robot_inquiry(q, user_name="Ayush")
        assert ans is not None
        assert "AI assistant" in ans or "automated" in ans.lower()
        assert "Ayush" in ans

    # Non-robot questions should return None
    assert handle_robot_inquiry("What is your name?", user_name="Ayush") is None
    assert handle_robot_inquiry("How can I help you?", user_name="Ayush") is None


def test_outcome_verifier_with_valid_confirmation_code():
    callee = CalleeInfo(name="Hotel Sunrise", phone_number="+919876543210")
    packet = FactsPacket(
        callee=callee,
        objective="Book room for 14 Dec",
        authority=AuthorityLevel.L2,
        budget_ceiling=5000.0
    )
    session = CallSession(packet=packet)
    session.transcript = [
        {"role": "callee", "text": "Your booking is confirmed. Your reservation ID is HSR-9482."}
    ]

    result = verify_booking_outcome(session)
    assert result.status == VerificationStatus.CONFIRMED
    assert result.confirmation_code == "HSR-9482"
    assert result.is_verified is True


def test_outcome_verifier_rejects_hallucinated_booking_without_code_or_sms():
    callee = CalleeInfo(name="Hotel Sunrise", phone_number="+919876543210")
    packet = FactsPacket(
        callee=callee,
        objective="Book room for 14 Dec",
        authority=AuthorityLevel.L2
    )
    session = CallSession(packet=packet)
    # Callee says okay but never gave a code or reference
    session.transcript = [
        {"role": "callee", "text": "Yeah yeah, I noted it down, see you then."}
    ]

    result = verify_booking_outcome(session)
    # Per Doc 33 Stage D & Doc 35 §6, verbal impression without code is UNVERIFIED!
    assert result.status == VerificationStatus.UNVERIFIED
    assert result.is_verified is False
    assert "No booking reference or confirmation code detected" in result.reason
