"""Facts Packet, Authority Envelope and Briefing Card Generator for Pico Telephony."""

import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from telephony.contact_resolver import CalleeInfo

class AuthorityLevel(str, Enum):
    L0 = "L0_ENQUIRE"         # Information gathering only, no booking/commitments
    L1 = "L1_HOLD"            # Place tentative hold/reservation, no payment
    L2 = "L2_BOOK"            # Commit/book within strict budget ceiling and dates
    L3 = "L3_APPROVAL_ONLY"   # Mid-call approval required for every commitment

@dataclass
class FactsPacket:
    callee: CalleeInfo
    objective: str
    authority: AuthorityLevel = AuthorityLevel.L0
    budget_ceiling: Optional[float] = None
    red_lines: List[str] = field(default_factory=list)
    allowed_facts: Dict[str, Any] = field(default_factory=dict)
    allowlist_confirmed: bool = False
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def is_call_authorized(self) -> bool:
        """
        Check if the call has passed all required authorization gates.
        For personal contacts from address book, requires explicit allowlist confirmation (Doc 35 §5).
        """
        if self.callee.source == "contacts" and not self.allowlist_confirmed:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "callee": self.callee.to_dict(),
            "objective": self.objective,
            "authority": self.authority.value,
            "budget_ceiling": self.budget_ceiling,
            "red_lines": list(self.red_lines),
            "allowed_facts": dict(self.allowed_facts),
            "allowlist_confirmed": self.allowlist_confirmed,
        }

def get_opening_disclosure_line(packet: FactsPacket, user_name: str = "Ayush") -> str:
    """
    Generate mandatory opening disclosure per Doc 29/33/35.
    Must state AI identity and on whose behalf the call is placed.
    """
    callee_name = packet.callee.name
    # Tailor for personal contacts vs businesses
    if packet.callee.source == "contacts":
        return f"Hello {callee_name}, I'm Pico, an AI assistant calling on behalf of {user_name}."
    return f"Hello, I'm Pico, an AI assistant calling on behalf of {user_name} regarding {packet.objective}."

def build_briefing_card(packet: FactsPacket) -> Dict[str, Any]:
    """
    Build the Telegram Ask-First Briefing Card.
    """
    ceiling_str = f"₹{packet.budget_ceiling:,.0f}" if packet.budget_ceiling else "None (No spend permitted)"
    red_lines_str = "\n".join(f"  • {r}" for r in packet.red_lines) if packet.red_lines else "  • Standard guardrails (no payments, no OTPs, no private data)"
    
    auth_desc = {
        AuthorityLevel.L0: "L0 — Enquire Only (No commitments)",
        AuthorityLevel.L1: "L1 — Hold / Reserve (Tentative only)",
        AuthorityLevel.L2: f"L2 — Book within ceiling ({ceiling_str})",
        AuthorityLevel.L3: "L3 — Strict Live Approval Required",
    }.get(packet.authority, packet.authority.value)

    text = (
        f"📋 <b>Pico Call Briefing Card</b>\n\n"
        f"👤 <b>Callee:</b> {packet.callee.name} (<code>{packet.callee.phone_number}</code>)\n"
        f"🎯 <b>Objective:</b> {packet.objective}\n"
        f"🛡️ <b>Authority Envelope:</b> {auth_desc}\n"
        f"💰 <b>Budget Ceiling:</b> {ceiling_str}\n"
        f"🚫 <b>Red Lines:</b>\n{red_lines_str}\n\n"
        f"Tap below to authorize and place the call via device SIM:"
    )

    buttons = [
        {"text": "📞 Confirm & Call", "callback_data": f"confirm_call_{packet.call_id}"},
        {"text": "✏️ Edit Details", "callback_data": f"edit_call_{packet.call_id}"},
        {"text": "❌ Cancel", "callback_data": f"cancel_call_{packet.call_id}"},
    ]

    return {
        "text": text,
        "buttons": buttons,
        "call_id": packet.call_id,
        "packet": packet
    }
