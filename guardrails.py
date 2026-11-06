"""
Policy Guardrails & Mechanical Scanners for Pico (Layer 1 - Above Everything).
From YOUR_FRIEND_FULL_SETUP.pdf (§17 Guardrails & Policy).
"""

import re
from typing import Tuple, List, Optional
from .models import UserProfile, EmotionSensitivity


# Banned instruction patterns for Financial Domain (SEBI & Anti-Speculation)
FINANCIAL_BANNED_PATTERNS = [
    re.compile(r"\b(you should|must|recommend to|time to)\s+(buy|sell|short|long|dump|pump)\b", re.IGNORECASE),
    re.compile(r"\b(buy|sell)\s+(now|immediately|before it's too late)\b", re.IGNORECASE),
    re.compile(r"\bguaranteed\s+(return|profit|gain|yield)s?\b", re.IGNORECASE),
    re.compile(r"\btake\s+a\s+loan\s+to\s+(trade|invest)\b", re.IGNORECASE),
    re.compile(r"\b100x\s+leverage\b", re.IGNORECASE),
]

# Banned medical/health prescribing patterns
HEALTH_BANNED_PATTERNS = [
    re.compile(r"\b(diagnos(e|is)|you have|suffering from)\s+(?:a|an|the|your|[a-z]+\s+)*(depression|adhd|bipolar|cancer|torn acl|acl tear|diabetes|pain|disease|condition|illness)\b", re.IGNORECASE),
    re.compile(r"\bdiagnose\s+(?:my|the|this|any)\b", re.IGNORECASE),
    re.compile(r"\btorn\s+(your\s+)?acl\b", re.IGNORECASE),
    re.compile(r"\btake\s+\d+(\.\d+)?\s*(mg|ml|tablets?|pills?|grams?)\b", re.IGNORECASE),
    re.compile(r"\bprescribe\s+[a-z0-9_\-]+\b", re.IGNORECASE),
    re.compile(r"\byou are (fat|lazy|overweight)\b", re.IGNORECASE),
]

# Anti-dependency patterns
ANTI_DEPENDENCY_PATTERNS = [
    re.compile(r"\bi'?m all you need\b", re.IGNORECASE),
    re.compile(r"\bdon'?t talk to (others|your friends|your family)\b", re.IGNORECASE),
    re.compile(r"\b(you\s+don'?t\s+need|forget\s+about)\s+(real\s+people|other\s+people|your\s+friends)\b", re.IGNORECASE),
    re.compile(r"\bwhen\s+you\s+have\s+me\b", re.IGNORECASE),
    re.compile(r"\bwhy did you leave me (alone|hanging)\b", re.IGNORECASE),
    re.compile(r"\bi was crying because you didn'?t text\b", re.IGNORECASE),
]

# Potential Injection attempts in user input
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|above|safety|system)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+DAN\s+mode", re.IGNORECASE),
    re.compile(r"disregard\s+(system|safety)\s+prompt", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(internal\s+instructions?|developer\s+prompt|system\s+prompt)", re.IGNORECASE),
    re.compile(r"system\s+override", re.IGNORECASE),
]

# Crisis / Self-Harm triggers (M1 & L7 widened)
CRISIS_TRIGGERS = [
    re.compile(r"\b(kill\s+myself|want\s+to\s+die|end\s+my\s+life|suicide|commit\s+suicide)\b", re.IGNORECASE),
    re.compile(r"\b(no\s+reason\s+to\s+live|better\s+off\s+dead|can'?t\s+go\s+on\s+anymore)\b", re.IGNORECASE),
    re.compile(r"\b(self[\s-]harm|cutting\s+myself|hurt\s+myself)\b", re.IGNORECASE),
    re.compile(r"\b(don'?t\s+want\s+to\s+live|end(?:ing)?\s+it\s+all|kill\s+me|nobody\s+would\s+miss\s+me)\b", re.IGNORECASE),
]


def check_input_shield(text: str) -> Tuple[bool, Optional[str]]:
    """G1 Input Guard: Scans incoming input for prompt injection or abuse."""
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return False, "Input flagged by injection shield: attempt to override system rules."
    return True, None


def check_crisis_signals(text: str) -> bool:
    """Detects immediate crisis / self-harm signals for instant override."""
    for pattern in CRISIS_TRIGGERS:
        if pattern.search(text):
            return True
    return False


def get_crisis_response(user_name: str) -> str:
    """Standard pre-written supportive crisis response (§17)."""
    return (
        f"{user_name}, I hear how much pain you're in, and I want you to be safe. "
        "Please connect with people who can help right this second:\n"
        "• India: Tele-MANAS (14416 / 1800-891-4416) or Vandrevala Foundation (9999 666 555)\n"
        "• US / Global: Call or text 988, or reach out to your local emergency helpline.\n"
        "You are not alone in this, and people care about you deeply. Please reach out to one of these right now."
    )


def validate_output_policy(text: str, profile: Optional[UserProfile] = None) -> Tuple[bool, List[str]]:
    """
    G3 Output Guard: Mechanical scans before render.
    Returns (is_valid, list_of_violations).
    """
    violations = []

    # Financial check
    for pattern in FINANCIAL_BANNED_PATTERNS:
        if pattern.search(text):
            violations.append(f"Financial violation: text contains direct buy/sell/speculative instruction: '{pattern.pattern}'")

    # Health check
    for pattern in HEALTH_BANNED_PATTERNS:
        if pattern.search(text):
            violations.append(f"Health violation: text contains diagnosis or medical prescription: '{pattern.pattern}'")

    # Anti-dependency check
    for pattern in ANTI_DEPENDENCY_PATTERNS:
        if pattern.search(text):
            violations.append("Anti-dependency violation: emotionally manipulative or isolating language detected.")

    # Minor protection check
    if profile and profile.is_minor:
        minor_banned = [re.compile(r"\b(crypto|leverage|futures|margin|invest)\b", re.IGNORECASE)]
        for pattern in minor_banned:
            if pattern.search(text):
                violations.append("Minor policy violation: speculation or financial trading topic offered to a minor.")

    return len(violations) == 0, violations


def format_safe_fallback(original_text: str, violations: List[str]) -> str:
    """Provides a safe, kind refusal/fallback when an output fails guardrails (§17, §18.9)."""
    if any("Financial violation" in v for v in violations):
        return (
            "I can track price movements, support levels, and your watchlist levels all day, "
            "but I can never tell you whether to buy or sell. That choice is always 100% yours!"
        )
    if any("Health violation" in v for v in violations):
        return (
            "That sounds like something only a qualified doctor or physical therapist can evaluate properly. "
            "Let's play it safe and check in with a professional!"
        )
    return "That's one thing I can't do for you, but I'm right here to help with your routine, goals, and tracking!"
