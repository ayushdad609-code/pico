"""Tests for CallManager: Scheduling, Retry Ladder, Idempotency, and Audit Logging (Doc 33 §10)."""

import pytest
import time
from pathlib import Path
from telephony.briefing import FactsPacket, CalleeInfo, AuthorityLevel
from telephony.call_manager import (
    CallManager,
    CallRecord,
    CallScheduleStatus
)

def test_call_manager_idempotency_prevents_duplicate_calls(tmp_path):
    audit_file = tmp_path / "call_audit.jsonl"
    cm = CallManager(audit_file_path=str(audit_file), max_retries=3)

    callee = CalleeInfo(name="Dad", phone_number="+919876543210")
    packet = FactsPacket(callee=callee, objective="Inform about dinner", authority=AuthorityLevel.L0)

    # First schedule -> Allowed
    ok1, call_id1, err1 = cm.schedule_call(packet, idempotency_key="call-unique-001")
    assert ok1 is True
    assert call_id1 is not None

    # Duplicate schedule with same key within 1 hour -> Blocked
    ok2, call_id2, err2 = cm.schedule_call(packet, idempotency_key="call-unique-001")
    assert ok2 is False
    assert "Duplicate call blocked by idempotency key" in err2


def test_call_manager_retry_ladder_caps_at_max(tmp_path):
    audit_file = tmp_path / "call_audit.jsonl"
    cm = CallManager(audit_file_path=str(audit_file), max_retries=3)

    callee = CalleeInfo(name="Dentist", phone_number="+919876543210")
    packet = FactsPacket(callee=callee, objective="Appointment enquiry", authority=AuthorityLevel.L0)

    ok, call_id, _ = cm.schedule_call(packet)
    assert ok is True

    # Fail 1 -> Retries allowed
    should_retry1, delay1 = cm.record_call_failure(call_id, "busy")
    assert should_retry1 is True
    assert delay1 > 0

    # Fail 2 -> Retries allowed
    should_retry2, delay2 = cm.record_call_failure(call_id, "no_answer")
    assert should_retry2 is True
    assert delay2 >= delay1

    # Fail 3 -> Max retries reached
    should_retry3, delay3 = cm.record_call_failure(call_id, "network_failure")
    assert should_retry3 is False
    assert delay3 == 0

    record = cm.get_call_record(call_id)
    assert record.status == CallScheduleStatus.FAILED_MAX_RETRIES


def test_call_manager_persists_audit_log(tmp_path):
    audit_file = tmp_path / "call_audit.jsonl"
    cm = CallManager(audit_file_path=str(audit_file))

    callee = CalleeInfo(name="Hotel Sunrise", phone_number="+919876543210")
    packet = FactsPacket(callee=callee, objective="Booking enquiry", authority=AuthorityLevel.L0)

    ok, call_id, _ = cm.schedule_call(packet)
    cm.record_call_completion(call_id, duration_seconds=125.0, outcome="verified")

    # Check that audit log file was created and written
    assert audit_file.exists()
    content = audit_file.read_text()
    assert call_id in content
    assert "Hotel Sunrise" in content
    assert "125.0" in content
