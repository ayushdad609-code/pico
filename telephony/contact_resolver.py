"""Contact Resolver & Phone Normalizer for Pico Telephony."""

import re
import json
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from device_sensors import SafeCommandRunner

logger = logging.getLogger(__name__)

@dataclass
class CalleeInfo:
    name: str
    phone_number: str
    source: str = "contacts"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "phone_number": self.phone_number,
            "source": self.source,
        }

def normalize_phone_number(raw: str, default_country: str = "+91") -> str:
    """Normalize raw phone strings to E.164-like clean numbers."""
    if not raw or not isinstance(raw, str):
        return ""
    
    # Check if there are letters
    if re.search(r"[a-zA-Z]", raw):
        return ""

    # Remove formatting characters
    cleaned = re.sub(r"[\s\-\(\)\.]", "", raw.strip())
    if not cleaned:
        return ""

    # If it starts with +, preserve it
    if cleaned.startswith("+"):
        digits_only = re.sub(r"\D", "", cleaned[1:])
        if len(digits_only) >= 7:
            return f"+{digits_only}"
        return ""

    # Digits only
    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        return ""

    # Handle 10-digit Indian numbers
    if len(digits) == 10:
        return f"{default_country}{digits}"
    # Handle leading 0 (e.g. 09876543210)
    elif len(digits) == 11 and digits.startswith("0"):
        return f"{default_country}{digits[1:]}"
    elif len(digits) >= 11:
        return f"+{digits}"
    
    return ""

async def resolve_callee(target: str, timeout: float = 2.0) -> Optional[CalleeInfo]:
    """
    Resolve a target (either a raw phone number or a contact name) to a CalleeInfo.
    Applies strict data minimization: never returns or leaks other contacts.
    """
    target_clean = target.strip()
    if not target_clean:
        return None

    # 1. Check if direct phone number
    normalized = normalize_phone_number(target_clean)
    if normalized:
        return CalleeInfo(
            name=normalized,
            phone_number=normalized,
            source="direct"
        )

    # 2. Query Termux contact list with SafeCommandRunner
    try:
        ok, stdout, _ = await SafeCommandRunner.run(["termux-contact-list"], timeout=timeout)
        if not ok or not stdout.strip():
            logger.warning("termux-contact-list failed or timed out.")
            return None

        contacts = json.loads(stdout)
        if not isinstance(contacts, list):
            return None

        query_lower = target_clean.lower()
        exact_match = None
        partial_match = None

        for c in contacts:
            c_name = c.get("name", "")
            c_number = c.get("number", "")
            if not c_name or not c_number:
                continue

            clean_num = normalize_phone_number(c_number)
            if not clean_num:
                continue

            name_lower = c_name.lower()
            if name_lower == query_lower:
                exact_match = CalleeInfo(name=c_name, phone_number=clean_num, source="contacts")
                break
            elif query_lower in name_lower and partial_match is None:
                partial_match = CalleeInfo(name=c_name, phone_number=clean_num, source="contacts")

        return exact_match or partial_match

    except Exception as e:
        logger.error(f"Error resolving contact '{target}': {e}")
        return None
