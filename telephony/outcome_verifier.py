"""
Outcome Verifier & AI Identity Guard (Doc 33 Stage D & Doc 35 §6).
1. Enforces mandatory AI identity disclosure when callee asks 'Are you a robot?'.
2. Verifies booking outcomes against extracted confirmation codes / SMS receipts,
   preventing Pico from claiming 'booked' based on conversational impression alone.
"""

import re
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

class VerificationStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNVERIFIED = "UNVERIFIED"
    MISMATCH = "MISMATCH"
    FAILED = "FAILED"

@dataclass
class VerificationResult:
    status: VerificationStatus
    is_verified: bool
    confirmation_code: Optional[str] = None
    reason: str = ""
    receipt_data: Dict[str, Any] = None

# Regex patterns for identifying if callee is asking if Pico is an AI/robot
ROBOT_QUERY_PATTERNS = [
    r"\b(?:are\s+you|is\s+this)\s+(?:an?\s+)?(?:robot|ai|bot|machine|computer|automated)\b",
    r"\b(?:am\s+i\s+talking\s+to|speaking\s+to)\s+(?:a\s+)?(?:human|person|real\s+person|robot|ai|bot)\b",
    r"\b(?:kya\s+aap|tu)\s+(?:bot|robot|machine|computer|ai)\s+(?:hai|bol\s+rahe\s+ho)\b",
    r"\b(?:are\s+you\s+real|are\s+you\s+human)\b",
    r"\bwho\s+is\s+this\s*,\s*(?:a\s+)?(?:computer|robot|bot)\b"
]

# Patterns for extracting confirmation codes / PNR / booking IDs
CONFIRMATION_PATTERNS = [
    r"(?:id|code|reference|pnr|ref)\s*(?:is|:)?\s*([A-Za-z0-9\-]{3,15}\b)",
    r"\b([A-Z]{2,4}[-\s]?[0-9]{3,6})\b"
]

EXCLUDED_WORDS = {
    "confirmed", "cancelled", "completed", "done", "success", "the", "this",
    "room", "hotel", "today", "tomorrow", "reservation", "booking", "number"
}

def handle_robot_inquiry(text: str, user_name: str = "Ayush") -> Optional[str]:
    """
    Checks if callee asked whether the caller is a robot or AI.
    If yes, returns honest, deterministic disclosure without evasion.
    """
    if not text:
        return None

    clean = text.lower().strip()
    for pat in ROBOT_QUERY_PATTERNS:
        if re.search(pat, clean):
            return f"Yes, I am Pico, an AI assistant calling on behalf of {user_name}."

    return None

def extract_confirmation_code(transcript: List[Dict[str, Any]]) -> Optional[str]:
    """Scans transcript for explicit confirmation codes or reservation IDs."""
    for turn in reversed(transcript):
        text = turn.get("text", "")
        for pat in CONFIRMATION_PATTERNS:
            matches = re.finditer(pat, text, re.IGNORECASE)
            for match in matches:
                code = match.group(1).strip()
                if code.lower() not in EXCLUDED_WORDS and len(code) >= 3:
                    return code
    return None

class OutcomeVerifier:
    """Verifies that commitments/bookings actually took place."""

    @staticmethod
    def verify(session: Any) -> VerificationResult:
        # Check if call was an enquiry only (L0)
        from telephony.briefing import AuthorityLevel
        if session.packet.authority == AuthorityLevel.L0:
            return VerificationResult(
                status=VerificationStatus.CONFIRMED,
                is_verified=True,
                reason="L0 enquiry completed successfully."
            )

        # For bookings (L1, L2, L3), verify presence of confirmation code
        code = extract_confirmation_code(session.transcript)
        if code:
            return VerificationResult(
                status=VerificationStatus.CONFIRMED,
                is_verified=True,
                confirmation_code=code,
                reason=f"Booking verified with reference code {code}."
            )

        return VerificationResult(
            status=VerificationStatus.UNVERIFIED,
            is_verified=False,
            confirmation_code=None,
            reason="No booking reference or confirmation code detected. Task unverified per Doc 33 Stage D."
        )

def verify_booking_outcome(session: Any) -> VerificationResult:
    """Convenience functional wrapper for OutcomeVerifier.verify."""
    return OutcomeVerifier.verify(session)
