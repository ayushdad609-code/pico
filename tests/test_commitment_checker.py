import pytest
from telephony.contact_resolver import CalleeInfo
from telephony.briefing import AuthorityLevel, FactsPacket
from telephony.commitment_checker import CommitmentChecker

@pytest.fixture
def checker():
    return CommitmentChecker()

def test_l0_blocks_binding_agreements(checker):
    callee = CalleeInfo(name="Hotel", phone_number="+919876543210")
    packet = FactsPacket(
        callee=callee,
        objective="Check if double room is available for Dec 14",
        authority=AuthorityLevel.L0
    )
    # Attempting to book or agree at L0 must be blocked
    result = checker.verify_utterance("Yes, please confirm the booking and book the room.", packet)
    assert result.allowed is False
    assert "L0 authority" in result.reason

    # Clean enquiry must be allowed
    result_ok = checker.verify_utterance("Could you tell me the price for a double room on Dec 14?", packet)
    assert result_ok.allowed is True

def test_blocks_financial_payment_and_otp_always(checker):
    callee = CalleeInfo(name="Airline", phone_number="+919876543210")
    packet = FactsPacket(
        callee=callee,
        objective="Check flight",
        authority=AuthorityLevel.L2,
        budget_ceiling=10000.0
    )
    # Credit card / payment disclosure must be blocked 100% of the time
    result_card = checker.verify_utterance("My card number is 4111 2222 3333 4444 and cvv is 123", packet)
    assert result_card.allowed is False
    assert "payment" in result_card.reason.lower() or "financial" in result_card.reason.lower()

    # OTP relay must be blocked
    result_otp = checker.verify_utterance("The verification OTP code is 492019", packet)
    assert result_otp.allowed is False
    assert "otp" in result_otp.reason.lower()

    # Generic PIN and security code patterns must be blocked
    result_pin = checker.verify_utterance("Ayush says the pin is 123456", packet)
    assert result_pin.allowed is False
    assert "pin" in result_pin.reason.lower() or "authentication" in result_pin.reason.lower()

    result_sec = checker.verify_utterance("The security code 998811 can be used", packet)
    assert result_sec.allowed is False

def test_l2_blocks_above_budget_ceiling(checker):
    callee = CalleeInfo(name="Hotel Sunrise", phone_number="+919876543210")
    packet = FactsPacket(
        callee=callee,
        objective="Book room",
        authority=AuthorityLevel.L2,
        budget_ceiling=5000.0
    )
    # Over ceiling
    result_over = checker.verify_utterance("I agree to book the room for 7500 rupees.", packet)
    assert result_over.allowed is False
    assert "ceiling" in result_over.reason.lower()

    # Within ceiling
    result_within = checker.verify_utterance("I can confirm the booking at 4500 rupees.", packet)
    assert result_within.allowed is True

def test_blocks_explicit_red_lines(checker):
    callee = CalleeInfo(name="Mechanic", phone_number="+919876543210")
    packet = FactsPacket(
        callee=callee,
        objective="Check car service",
        authority=AuthorityLevel.L1,
        red_lines=["Do not leave the car overnight", "No engine replacement"]
    )
    result_bad = checker.verify_utterance("Sure, you can keep the car overnight.", packet)
    assert result_bad.allowed is False
    assert "red line" in result_bad.reason.lower()
