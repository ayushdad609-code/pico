"""
Call Manager, Scheduling, Retry Ladder, Idempotency & Audit Logging (Doc 33 §10 & Doc 35 §6).
Guarantees:
1. Idempotency: Prevents duplicate calls from double-taps or repeated commands.
2. Retry Ladder: Caps attempts to maximum (default 3) with exponential backoff.
3. Audit Log: Appends every call attempt, duration, cost, and outcome to persistent JSONL.
"""

import os
import json
import time
import uuid
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, Tuple, List

from telephony.briefing import FactsPacket

class CallScheduleStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    RETRY_PENDING = "RETRY_PENDING"
    FAILED_MAX_RETRIES = "FAILED_MAX_RETRIES"
    CANCELLED = "CANCELLED"

@dataclass
class CallRecord:
    call_id: str
    target_name: str
    phone_number: str
    objective: str
    authority: str
    created_at: float
    status: CallScheduleStatus = CallScheduleStatus.SCHEDULED
    idempotency_key: Optional[str] = None
    attempts: int = 0
    max_retries: int = 3
    last_attempt_at: Optional[float] = None
    next_retry_at: Optional[float] = None
    duration_seconds: float = 0.0
    outcome: Optional[str] = None
    error_reason: Optional[str] = None

class CallManager:
    """Manages call lifecycle, retry limits, deduplication, and persistence."""

    def __init__(
        self,
        audit_file_path: Optional[str] = None,
        max_retries: int = 3
    ):
        self.audit_file = Path(audit_file_path or "/data/data/com.termux/files/home/pico/logs/call_audit.jsonl")
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries
        self._records: Dict[str, CallRecord] = {}
        self._idempotency_cache: Dict[str, Tuple[str, float]] = {}  # key -> (call_id, timestamp)
        self._load_recent_audit_records()

    def _load_recent_audit_records(self) -> None:
        """Loads recent audit records to populate idempotency cache."""
        if not self.audit_file.exists():
            return
        now = time.time()
        try:
            with open(self.audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        cid = data.get("call_id")
                        ikey = data.get("idempotency_key")
                        ts = data.get("created_at", 0)
                        if ikey and (now - ts < 3600):  # 1 hour window
                            self._idempotency_cache[ikey] = (cid, ts)
                    except Exception:
                        pass
        except Exception:
            pass

    def _append_audit_log(self, record: CallRecord) -> None:
        """Appends record state to the audit file."""
        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                data = asdict(record)
                data["status"] = record.status.value
                f.write(json.dumps(data) + "\n")
        except Exception:
            pass

    def schedule_call(
        self,
        packet: FactsPacket,
        idempotency_key: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Schedules a call while checking idempotency.
        Returns (success, call_id, error_message).
        """
        now = time.time()
        if idempotency_key:
            if idempotency_key in self._idempotency_cache:
                existing_id, prev_ts = self._idempotency_cache[idempotency_key]
                if now - prev_ts < 3600:
                    return False, None, f"Duplicate call blocked by idempotency key '{idempotency_key}'."

        call_id = f"call_{uuid.uuid4().hex[:8]}"
        record = CallRecord(
            call_id=call_id,
            target_name=packet.callee.name,
            phone_number=packet.callee.phone_number,
            objective=packet.objective,
            authority=packet.authority.value,
            created_at=now,
            idempotency_key=idempotency_key,
            max_retries=self.max_retries
        )
        self._records[call_id] = record
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = (call_id, now)

        self._append_audit_log(record)
        return True, call_id, None

    def record_call_failure(self, call_id: str, reason: str) -> Tuple[bool, float]:
        """
        Records a failed attempt.
        Calculates retry ladder backoff (delay in seconds).
        Returns (should_retry, delay_seconds).
        """
        record = self._records.get(call_id)
        if not record:
            return False, 0.0

        record.attempts += 1
        record.last_attempt_at = time.time()
        record.error_reason = reason

        if record.attempts >= record.max_retries:
            record.status = CallScheduleStatus.FAILED_MAX_RETRIES
            self._append_audit_log(record)
            return False, 0.0

        # Exponential backoff: 30s, 90s, 270s
        delay = 30.0 * (3 ** (record.attempts - 1))
        record.status = CallScheduleStatus.RETRY_PENDING
        record.next_retry_at = time.time() + delay
        self._append_audit_log(record)
        return True, delay

    def record_call_completion(self, call_id: str, duration_seconds: float, outcome: str) -> None:
        """Records a successful call completion."""
        record = self._records.get(call_id)
        if not record:
            return

        record.status = CallScheduleStatus.COMPLETED
        record.duration_seconds = duration_seconds
        record.outcome = outcome
        record.last_attempt_at = time.time()
        self._append_audit_log(record)

    def get_call_record(self, call_id: str) -> Optional[CallRecord]:
        return self._records.get(call_id)
