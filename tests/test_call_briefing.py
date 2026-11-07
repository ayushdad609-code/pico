import pytest
from telephony.contact_resolver import CalleeInfo
from telephony.briefing import (
    AuthorityLevel,
    FactsPacket,
    build_briefing_card,
    get_opening_disclosure_line,
)

def test_facts_packet_creation_and_briefing():
    callee = CalleeInfo(name="Dad", phone_number="+919876543210", source="contacts")
    packet = FactsPacket(
        callee=callee,
        objective="Tell him I'll be home by 8:30 PM",
        authority=AuthorityLevel.L0,
        budget_ceiling=None,
        red_lines=["Do not agree to buy anything over ₹500"],
        allowed_facts={"eta": "8:30 PM"},
        allowlist_confirmed=True
    )
    card = build_briefing_card(packet)
    assert "Dad" in card["text"]
    assert "+919876543210" in card["text"]
    assert "8:30 PM" in card["text"]
    assert "L0" in card["text"]
    assert "Do not agree to buy anything over ₹500" in card["text"]
    
    # Verify 3 interactive buttons
    assert len(card["buttons"]) == 3
    callbacks = [b["callback_data"] for b in card["buttons"]]
    assert any("confirm_call" in c for c in callbacks)
    assert any("edit_call" in c for c in callbacks)
    assert any("cancel_call" in c for c in callbacks)

def test_opening_disclosure_line_includes_ai_identity():
    # Doc 35 / Doc 29 mandatory AI disclosure
    callee = CalleeInfo(name="Hotel Sunrise", phone_number="+919876543210", source="manual")
    packet = FactsPacket(
        callee=callee,
        objective="Enquire room price",
        authority=AuthorityLevel.L0,
        budget_ceiling=None,
        red_lines=[],
        allowed_facts={}
    )
    disclosure = get_opening_disclosure_line(packet, user_name="Ayush")
    assert "AI assistant" in disclosure
    assert "Ayush" in disclosure

def test_personal_contact_requires_allowlist_gate():
    # Doc 35 §5: Personal contacts require explicit allowlist check
    callee = CalleeInfo(name="Dad", phone_number="+919876543210", source="contacts")
    packet = FactsPacket(
        callee=callee,
        objective="Ask about dinner",
        authority=AuthorityLevel.L0,
        budget_ceiling=None,
        red_lines=[],
        allowed_facts={},
        allowlist_confirmed=False
    )
    assert packet.is_call_authorized() is False
    packet.allowlist_confirmed = True
    assert packet.is_call_authorized() is True
