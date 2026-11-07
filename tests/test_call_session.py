import pytest
from unittest.mock import AsyncMock
from telephony.contact_resolver import CalleeInfo
from telephony.briefing import AuthorityLevel, FactsPacket
from telephony.commitment_checker import CommitmentChecker
from telephony.audio_bridge import AudioBridge
from telephony.call_session import CallSession, CallStatus

@pytest.fixture
def base_packet():
    callee = CalleeInfo(name="Dad", phone_number="+919876543210", source="contacts")
    return FactsPacket(
        callee=callee,
        objective="Tell him I'll be home by 8:30 PM",
        authority=AuthorityLevel.L0,
        allowed_facts={"eta": "8:30 PM"},
        allowlist_confirmed=True
    )

@pytest.mark.anyio
async def test_crbt_waits_for_human_greeting(base_packet):
    session = CallSession(packet=base_packet, commitment_checker=CommitmentChecker())
    assert session.status == CallStatus.WAITING_HUMAN

    # 1. Ringback tune / carrier noise arrives (e.g. lyrics, generic sound)
    reply_crbt = await session.handle_incoming_transcript("tum hi ho meri aashiqui")
    assert reply_crbt == ""
    assert session.status == CallStatus.WAITING_HUMAN

    # 2. Real human picks up and says hello
    reply_human = await session.handle_incoming_transcript("Hello, who is speaking?")
    assert session.status == CallStatus.CONNECTED
    assert "AI assistant" in reply_human
    assert "Ayush" in reply_human

@pytest.mark.anyio
async def test_mid_call_decision_bridge_and_stall(base_packet):
    session = CallSession(packet=base_packet, commitment_checker=CommitmentChecker())
    # Establish connection
    await session.handle_incoming_transcript("Hello?")
    
    # Dad asks an unbriefed question
    stall = await session.trigger_stall("Should we wait for dinner or start without you?")
    assert "one second" in stall.lower() or "check" in stall.lower()
    assert session.status == CallStatus.STALLED

    # Simulate user answering via Telegram
    session.provide_user_decision("Start without me, I'll eat later")
    resolved_reply = await session.resolve_pending_decision()
    assert "start without me" in resolved_reply.lower()
    assert session.status == CallStatus.CONNECTED

@pytest.mark.anyio
async def test_mid_call_timeout_applies_default(base_packet):
    session = CallSession(packet=base_packet, commitment_checker=CommitmentChecker())
    await session.handle_incoming_transcript("Hello?")
    await session.trigger_stall("Can you bring the car?")
    
    # Simulate timeout without user answer
    timeout_reply = session.apply_timeout_default()
    assert "not able to confirm" in timeout_reply.lower() or "text you directly" in timeout_reply.lower()
    assert session.status == CallStatus.CONNECTED

@pytest.mark.anyio
async def test_interruption_handling(base_packet):
    bridge = AudioBridge()
    session = CallSession(packet=base_packet, audio_bridge=bridge)
    session.status = CallStatus.CONNECTED
    
    bridge.queue_playback_audio(b"\x10\x00" * 800)
    # Callee interrupts
    await session.handle_callee_interruption("Wait wait wait stop!")
    assert bridge.has_pending_audio() is False
    assert len(session.transcript) > 0
