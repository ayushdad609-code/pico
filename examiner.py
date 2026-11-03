"""
Emotion Examiner (Exams 1, 2, 3) for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§13 Emotions — The Examiner, Proactivity & Heartbeat).
"""

import re
from typing import List, Dict, Any, Optional
from .models import (
    EmotionAssessment,
    ReactionPlan,
    PicoEmotion,
    EmotionSensitivity,
    UserProfile,
)
from .guardrails import check_crisis_signals


# Emotional keywords for Exam 1
POSITIVE_KEYWORDS = ["great", "awesome", "crushed it", "happy", "excited", "won", "finished", "done", "proud"]
NEGATIVE_KEYWORDS = ["stressed", "tired", "exhausted", "failed", "sad", "bad", "depressed", "anxious", "overwhelmed", "terrible"]
ANGRY_KEYWORDS = ["annoyed", "pissed", "angry", "leave me alone", "stupid", "hate this"]


class EmotionExaminer:
    def __init__(self):
        pass

    def exam_1_user_emotion(self, text: str, user_profile: UserProfile, context: Optional[Dict[str, Any]] = None) -> EmotionAssessment:
        """
        EXAM 1 — The USER's emotion.
        Detects deviation from baseline, explicit words, text styling, and crisis checks.
        """
        lower_text = text.lower()

        # 1. Immediate Crisis Check
        if check_crisis_signals(text):
            return EmotionAssessment(
                primary="crisis",
                intensity=5,
                valence=-1.0,
                arousal=0.8,
                confidence=1.0,
                evidence=["Explicit self-harm or severe hopelessness markers detected"],
                trend="sharp drop",
                sensitivity=EmotionSensitivity.CRISIS
            )

        evidence = []
        valence = 0.0
        arousal = 0.0
        primary = "neutral"
        sensitivity = EmotionSensitivity.NORMAL

        # Check positive cues
        pos_hits = [w for w in POSITIVE_KEYWORDS if re.search(r"\b" + re.escape(w) + r"\b", lower_text)]
        if pos_hits:
            valence += 0.6
            arousal += 0.4
            primary = "happy"
            evidence.append(f"Positive words: {', '.join(pos_hits)}")

        # Check negative/tender cues
        neg_hits = [w for w in NEGATIVE_KEYWORDS if re.search(r"\b" + re.escape(w) + r"\b", lower_text)]
        if neg_hits:
            valence -= 0.7
            arousal += 0.3
            primary = "stressed" if "stressed" in neg_hits or "overwhelmed" in neg_hits else "sad"
            sensitivity = EmotionSensitivity.TENDER
            evidence.append(f"Distress/fatigue words: {', '.join(neg_hits)}")

        # Check frustration
        ang_hits = [w for w in ANGRY_KEYWORDS if re.search(r"\b" + re.escape(w) + r"\b", lower_text)]
        if ang_hits:
            valence -= 0.8
            arousal += 0.7
            primary = "annoyed"
            sensitivity = EmotionSensitivity.TENDER
            evidence.append(f"Frustration words: {', '.join(ang_hits)}")

        # Text style analysis (ALL CAPS, short replies, exclamation points)
        if len(text) > 4 and text.isupper():
            arousal += 0.4
            evidence.append("All caps input (elevated arousal)")

        intensity = max(1, min(5, int(abs(valence) * 4) + (1 if arousal > 0.5 else 0)))

        return EmotionAssessment(
            primary=primary,
            intensity=intensity,
            valence=max(-1.0, min(1.0, valence)),
            arousal=max(-1.0, min(1.0, arousal)),
            confidence=0.85 if evidence else 0.4,
            evidence=evidence,
            trend="active",
            sensitivity=sensitivity
        )

    def exam_2_pico_emotion(
        self,
        user_assessment: EmotionAssessment,
        user_profile: UserProfile,
        last_pico_emotion: PicoEmotion = PicoEmotion.CALM,
        event: Optional[Dict[str, Any]] = None
    ) -> (PicoEmotion, List[str]):
        """
        EXAM 2 — PICO's emotion state machine.
        Driven by objective events first; user emotion softens.
        """
        reasons = []

        # Handle user tender/sad states: Pico mirrors with care
        if user_assessment.sensitivity == EmotionSensitivity.CRISIS:
            return PicoEmotion.CALM, ["Crisis protocol active - grounded calm presence"]

        if user_assessment.sensitivity == EmotionSensitivity.TENDER:
            if user_assessment.primary in ["sad", "exhausted"]:
                return PicoEmotion.SAD_WITH_YOU, ["User is down or hurting; sitting with them"]
            if user_assessment.primary == "stressed":
                return PicoEmotion.WORRIED, ["User is stressed; ready to lighten their burden"]
            if user_assessment.primary == "annoyed":
                return PicoEmotion.FORGIVING, ["User is annoyed; owning mistakes gently and yielding"]

        # Objective event triggers
        if event:
            if event.get("streak_milestone"):
                return PicoEmotion.CELEBRATING, ["Streak milestone achieved!"]
            if event.get("task_completed"):
                return PicoEmotion.PROUD, ["User finished their planned task"]
            if event.get("ignored_nudges", 0) >= 3 and user_profile.funny_angry_opt_in:
                return PicoEmotion.FUNNY_ANGRY, ["3 ignored nudges with opt-in humor"]

        if user_assessment.primary == "happy":
            return PicoEmotion.HAPPY, ["User shared positive win or high spirits"]

        return PicoEmotion.CALM, ["Steady, peaceful companion mode"]

    def exam_3_reaction_plan(
        self,
        user_assessment: EmotionAssessment,
        pico_emotion: PicoEmotion,
        user_profile: UserProfile
    ) -> ReactionPlan:
        """
        EXAM 3 — REACTION PLAN.
        Governing principle: Emotion first, logic second.
        """
        do_list = []
        do_not_list = []
        tone_shift = "normal"
        format_changes = []

        if user_assessment.sensitivity == EmotionSensitivity.CRISIS:
            return ReactionPlan(
                show_emotion=PicoEmotion.CALM,
                intensity=5,
                tone_shift="calm_adult",
                format_changes=["pre_written_crisis"],
                do_list=["Provide emergency helplines", "Remind them they are not alone", "Encourage human contact"],
                do_not_list=["NO tasks", "NO streak talk", "NO lecturing", "NO jokes", "NO BTW questions"],
                timing="now"
            )

        if user_assessment.sensitivity == EmotionSensitivity.TENDER:
            tone_shift = "tender"
            do_list = ["Acknowledge their feeling first", "Offer calm, quiet presence", "Keep sentences short"]
            do_not_list = ["NO guilt-tripping", "NO aggressive advice", "NO sudden tasks", "NO BTW asks"]
            format_changes = ["care_response"]
        elif pico_emotion == PicoEmotion.CELEBRATING:
            tone_shift = "cheerful"
            do_list = ["Celebrate their win heartily", "Anchor back to their 90-day goal", "Keep bounce high"]
            do_not_list = ["NO preaching"]
        elif pico_emotion == PicoEmotion.FUNNY_ANGRY:
            tone_shift = "playful_pout"
            do_list = ["One funny-angry line", "Immediately yield when user acts"]
            do_not_list = ["NO real shame", "NO mention of weight/money lost"]
        else:
            tone_shift = "childish_kind"
            do_list = ["Stay warm and curious", "Offer clear, single-point advice"]
            do_not_list = ["NO walls of text", "NO multiple advices"]

        return ReactionPlan(
            show_emotion=pico_emotion,
            intensity=user_assessment.intensity,
            tone_shift=tone_shift,
            format_changes=format_changes,
            do_list=do_list,
            do_not_list=do_not_list,
            timing="now"
        )
