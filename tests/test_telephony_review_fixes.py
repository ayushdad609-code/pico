"""Regression tests for code review findings from Principal Reviewer."""

import pytest
from unittest.mock import patch, AsyncMock
from telephony.contact_resolver import CalleeInfo
from telephony.briefing import AuthorityLevel, FactsPacket
from telephony.commitment_checker import CommitmentChecker
from telephony.audio_bridge import AudioBridge
from telephony.call_session import CallSession, CallStatus
from skills.telephony_skill import TelephonySkill
from skills.base_skill import SkillResult

@pytest.mark.anyio
async def test_commitment_checker_bypass_prevented_in_call_session():
    callee = CalleeInfo(name="Hotel", phone_number="+919876543210")
    packet = FactsPacket(callee=callee, objective="Tariff check", authority=AuthorityLevel.L0)
    session = CallSession(packet=packet, commitment_checker=CommitmentChecker())
    session.status = CallStatus.CONNECTED

    await session.trigger_stall("Should I book it for 5000?")
    # User tries to approve a booking that violates L0
    session.provide_user_decision("Yes, please confirm the booking and book the room.")
    
    reply = await session.resolve_pending_decision()
    # Must NOT speak the forbidden text!
    assert "confirm the booking" not in reply.lower()
    assert "cannot authorize" in reply.lower() or "directly" in reply.lower()

def test_telephony_skill_execute_returns_valid_skill_result():
    skill = TelephonySkill()
    res = skill.execute({"action": "resolve", "target": "+919876543210"})
    assert isinstance(res, SkillResult)
    assert res.success is True
    assert res.skill_name == "telephony_skill"
    assert res.output["phone_number"] == "+919876543210"
    assert res.execution_time_ms >= 0.0

def test_authority_envelope_l1_blocks_booking():
    checker = CommitmentChecker()
    callee = CalleeInfo(name="Hotel", phone_number="+919876543210")
    packet = FactsPacket(callee=callee, objective="Hold room", authority=AuthorityLevel.L1)
    
    # At L1, booking verbs must be blocked
    res = checker.verify_utterance("Please confirm the booking and book the room.", packet)
    assert res.allowed is False
    assert "L1 authority" in res.reason or "booking" in res.reason.lower()

def test_instant_interruption_flushes_buffer_immediately():
    bridge = AudioBridge(sample_rate=16000)
    bridge.queue_playback_audio(b"\x10\x00" * 3200) # 100ms
    assert bridge.has_pending_audio() is True

    # Incoming speech
    speech_frame = b"\x70\x70" * 320
    is_speech = bridge.on_microphone_frame(speech_frame)
    assert is_speech is True
    assert bridge.is_interrupted() is True
    # Buffer must be flushed immediately (<50ms cutoff)
    assert bridge.has_pending_audio() is False

@pytest.mark.anyio
async def test_standalone_haan_greeting_matches():
    callee = CalleeInfo(name="Uncle", phone_number="+919876543210")
    packet = FactsPacket(callee=callee, objective="Say hi", authority=AuthorityLevel.L0)
    session = CallSession(packet=packet)

    assert session.status == CallStatus.WAITING_HUMAN
    # Standalone "haan" or "haan?"
    reply = await session.handle_incoming_transcript("haan?")
    assert session.status == CallStatus.CONNECTED
    assert "AI assistant" in reply
