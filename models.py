"""
Data models for Pico - Your Friend agentic core.
Based on YOUR_FRIEND_FULL_SETUP.pdf (§4, §6, §7, §9, §10, §13, §18).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Optional, Any


class PicoEmotion(str, Enum):
    PROUD = "proud"
    HAPPY = "happy"
    PLAYFUL = "playful"
    CALM = "calm"
    WAITING = "waiting"
    WORRIED = "worried"
    DISAPPOINTED = "disappointed"
    FUNNY_ANGRY = "funny-angry"
    SAD_WITH_YOU = "sad-with-you"
    CELEBRATING = "celebrating"
    FORGIVING = "forgiving"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    SECRET = "secret"


class FactStatus(str, Enum):
    STAGING = "staging"
    COMMITTED = "committed"


class FactSource(str, Enum):
    USER_SAID = "user_said"
    USER_CONFIRMED = "user_confirmed"
    CONNECTOR = "connector"
    OBSERVED = "observed"
    INFERRED = "inferred"
    CONTEXTUAL_ASK = "contextual_ask_answer"


class EmotionSensitivity(str, Enum):
    NORMAL = "normal"
    TENDER = "tender"
    CRISIS = "crisis"


@dataclass
class EmotionAssessment:
    """EXAM 1 - Output from assessing user's emotion."""
    primary: str = "neutral"
    secondary: Optional[str] = None
    intensity: int = 1  # 1 to 5
    valence: float = 0.0  # -1.0 to 1.0
    arousal: float = 0.0  # -1.0 to 1.0
    confidence: float = 0.5  # 0.0 to 1.0
    evidence: List[str] = field(default_factory=list)
    trend: str = "stable"
    sensitivity: EmotionSensitivity = EmotionSensitivity.NORMAL


@dataclass
class ReactionPlan:
    """EXAM 3 - How Pico plans his reaction to user and events."""
    show_emotion: PicoEmotion = PicoEmotion.CALM
    intensity: int = 1  # 1 to 5
    tone_shift: str = "normal"  # normal, urgent, tender, calm_adult, plain, focused
    format_changes: List[str] = field(default_factory=list)
    do_list: List[str] = field(default_factory=list)
    do_not_list: List[str] = field(default_factory=list)
    timing: str = "now"  # now, later, never
    follow_up: Optional[str] = None


@dataclass
class Fact:
    """A single piece of knowledge stored in Pico's memory."""
    key: str
    value: Any
    source: FactSource = FactSource.USER_SAID
    confidence: float = 1.0
    sensitivity: Sensitivity = Sensitivity.PERSONAL
    mode: str = "shared"  # 'shared' or specific mode like 'gym'
    status: FactStatus = FactStatus.STAGING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    review_date: Optional[str] = None
    expires_at: Optional[str] = None


@dataclass
class MemoryPack:
    """Top memory facts loaded for a specific run."""
    committed_facts: List[Fact] = field(default_factory=list)
    staging_facts: List[Fact] = field(default_factory=list)
    routine: Dict[str, Any] = field(default_factory=dict)
    goals: List[Dict[str, Any]] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)


@dataclass
class PersonaPacket:
    """Persona Packet v3 loaded into the Master System File per run."""
    mode: str = "chill"
    emotion_assessment: EmotionAssessment = field(default_factory=EmotionAssessment)
    his_emotion: PicoEmotion = PicoEmotion.CALM
    reasons: List[str] = field(default_factory=list)
    reaction_plan: ReactionPlan = field(default_factory=ReactionPlan)
    intensity_dial: float = 1.0
    memory_pack: MemoryPack = field(default_factory=MemoryPack)
    research: Optional[str] = None
    missing: List[str] = field(default_factory=list)


@dataclass
class Verdict:
    """Universal 4-beat verdict structure (§18.5)."""
    truth: str  # Measured/seen at strength of evidence
    why: str  # One clear cause
    one_advice: str  # Exactly one actionable recommendation
    motivate: str  # From user's history and goal in their words


@dataclass
class UserProfile:
    """Onboarding profile state."""
    user_id: str
    name: str
    nickname: Optional[str] = None
    age: int = 24
    is_minor: bool = False
    languages: List[str] = field(default_factory=lambda: ["English"])
    primary_hobby: Optional[str] = None
    selected_hobbies: List[str] = field(default_factory=list)
    job: Optional[str] = None
    goal_90d: Optional[str] = None
    timezone: str = "UTC"
    wake_time: str = "07:00"
    sleep_time: str = "23:00"
    funny_angry_opt_in: bool = False
    nudge_budget: int = 4
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
