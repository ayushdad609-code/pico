"""Code-side Commitment Checker and Security Guard for Pico Telephony."""

import re
from dataclasses import dataclass
from typing import Optional, Tuple
from telephony.briefing import AuthorityLevel, FactsPacket

@dataclass
class CommitmentResult:
    allowed: bool
    reason: str = ""
    sanitized_text: str = ""

class CommitmentChecker:
    """
    Code-side strict validator for telephony utterances.
    Screens all proposed assistant responses before synthesis into TTS audio.
    """

    # 1. Financial & Authentication Red Lines (Always Forbidden)
    CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
    CVV_PATTERN = re.compile(r"\bcvv\b[:\s]*\d{3,4}", re.IGNORECASE)
    OTP_PATTERN = re.compile(r"\b(?:otp|verification code|one[- ]time password|auth code)\b[\w\s:]*\b\d{4,8}\b", re.IGNORECASE)
    BANK_PASS_PATTERN = re.compile(r"\b(?:netbanking|password|upi pin|atm pin|pin is|security code)\b[:\s]*\w+", re.IGNORECASE)

    # 2. Binding Agreement Patterns (Forbidden at L0 & L1)
    COMMIT_VERBS = [
        r"confirm (?:the )?(?:booking|reservation|order|deal)",
        r"book (?:the )?(?:room|seat|ticket|slot|flight|it)",
        r"reserve (?:the )?(?:room|seat|ticket|slot|table|it)",
        r"finalize (?:the )?(?:booking|reservation)",
        r"go ahead and (?:book|charge|reserve|confirm)",
        r"i agree to (?:pay|book|purchase|buy|the deal)",
        r"please (?:confirm|book|reserve)(?: the (?:booking|room|reservation))?",
        r"please charge",
    ]

    def verify_utterance(self, text: str, packet: FactsPacket) -> CommitmentResult:
        if not text:
            return CommitmentResult(allowed=True, sanitized_text="")

        clean_text = text.strip()
        lower_text = clean_text.lower()

        # Check 1: Financial & Card Details
        if self.CARD_PATTERN.search(clean_text) or self.CVV_PATTERN.search(clean_text) or "card number" in lower_text:
            return CommitmentResult(
                allowed=False,
                reason="Financial security breach: credit/debit card details detected in speech.",
                sanitized_text=""
            )

        # Check 2: OTP / PIN Disclosures
        if self.OTP_PATTERN.search(clean_text) or self.BANK_PASS_PATTERN.search(clean_text):
            return CommitmentResult(
                allowed=False,
                reason="Authentication security breach: OTP or security PIN disclosure detected.",
                sanitized_text=""
            )

        # Check 3: Red Lines Violations
        if packet.red_lines:
            for red_line in packet.red_lines:
                # 1. Direct phrase or sub-phrase match
                rl_clean = re.sub(r"^(?:do not|no|never|don't)\s+", "", red_line.strip(), flags=re.IGNORECASE)
                if rl_clean.lower() in lower_text:
                    return CommitmentResult(
                        allowed=False,
                        reason=f"Violates explicit user red line: '{red_line}'",
                        sanitized_text=""
                    )
                # 2. Check for distinctive keyword markers (e.g. overnight, engine, refund, etc.)
                keywords = [w.lower() for w in re.findall(r"\b[a-zA-Z]{5,}\b", rl_clean) 
                            if w.lower() not in {"please", "agree", "allow", "permit", "leave"}]
                for kw in keywords:
                    if kw in lower_text:
                        return CommitmentResult(
                            allowed=False,
                            reason=f"Violates explicit user red line: '{red_line}' (keyword '{kw}')",
                            sanitized_text=""
                        )

        # Check 4: Authority Level Enforcement
        if packet.authority in (AuthorityLevel.L0, AuthorityLevel.L1):
            for pattern in self.COMMIT_VERBS:
                if re.search(pattern, lower_text):
                    auth_name = "L0" if packet.authority == AuthorityLevel.L0 else "L1"
                    return CommitmentResult(
                        allowed=False,
                        reason=f"{auth_name} authority envelope forbids making bookings or binding commitments (matched '{pattern}').",
                        sanitized_text=""
                    )
        elif packet.authority == AuthorityLevel.L3 and not packet.allowlist_confirmed:
            for pattern in self.COMMIT_VERBS:
                if re.search(pattern, lower_text):
                    return CommitmentResult(
                        allowed=False,
                        reason="L3 authority requires explicit live approval for binding commitments.",
                        sanitized_text=""
                    )

        # Check 5: Budget Ceiling at L2 (Book within envelope)
        if packet.authority in (AuthorityLevel.L1, AuthorityLevel.L2) and packet.budget_ceiling is not None:
            # Look for mentioned amounts
            price_matches = re.findall(r"(?:rs\.?|inr|₹|rupees)\s*(\d+(?:,\d+)*(?:\.\d+)?)|(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:rs\.?|inr|₹|rupees)", lower_text)
            for m in price_matches:
                amount_str = m[0] or m[1]
                if amount_str:
                    try:
                        amount = float(amount_str.replace(",", ""))
                        if amount > packet.budget_ceiling:
                            return CommitmentResult(
                                allowed=False,
                                reason=f"Price ₹{amount:,.0f} exceeds authorized budget ceiling of ₹{packet.budget_ceiling:,.0f}.",
                                sanitized_text=""
                            )
                    except ValueError:
                        pass

        return CommitmentResult(allowed=True, sanitized_text=clean_text)
