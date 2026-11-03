"""
LLM Router and Privacy Guard for Pico.
From 32_FREE_BACKEND.pdf (§4 Free LLM Routing, §5 Privacy Catch)
and YOUR_FRIEND_FULL_SETUP.pdf (§10, §16, §18).
"""

import os
import re
from typing import Dict, Any, Optional, List
from .guardrails import validate_output_policy, format_safe_fallback, get_crisis_response
from .models import UserProfile, EmotionSensitivity, PersonaPacket


class LLMRouter:
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.litellm_url = os.getenv("LITELLM_URL", "http://localhost:4000")

    def route_and_generate(
        self,
        system_prompt: str,
        user_message: str,
        packet: PersonaPacket,
        profile: UserProfile,
        step: str = "step_5_verdict"
    ) -> str:
        """
        Routes the generation through the appropriate provider with privacy enforcement.
        Falls back to local intelligent generation if no API keys are present.
        """
        # Crisis override: immediate mechanical response
        if packet.emotion_assessment.sensitivity == EmotionSensitivity.CRISIS:
            return get_crisis_response(profile.name)

        # Enforce §5 Privacy Rule: Never send memory packs to free Gemini
        has_personal_context = bool(packet.memory_pack.committed_facts or packet.memory_pack.staging_facts)

        # If Groq is available, we can call it (Groq does not train on API requests by default)
        if self.groq_api_key:
            try:
                import httpx
                headers = {
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json"
                }
                # Step 5 uses 70b; extraction uses 8b
                model = "llama-3.3-70b-versatile" if step == "step_5_verdict" else "llama-3.1-8b-instant"
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 350
                }
                response = httpx.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=12.0)
                if response.status_code == 200:
                    raw_text = response.json()["choices"][0]["message"]["content"]
                    return self._guardrail_filter(raw_text, profile)
            except Exception as e:
                # Log fallthrough to next rung
                pass

        # If Gemini is available and allowed (NO personal context, or research only)
        if self.gemini_api_key and not has_personal_context:
            try:
                import httpx
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": f"System:\n{system_prompt}\n\nUser:\n{user_message}"}
                        ]
                    }]
                }
                response = httpx.post(url, json=payload, timeout=12.0)
                if response.status_code == 200:
                    raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return self._guardrail_filter(raw_text, profile)
            except Exception:
                pass

        # Native / Local Fallback Engine (Childish & Kind generator)
        return self._local_pico_engine(user_message, packet, profile)

    def _guardrail_filter(self, text: str, profile: UserProfile) -> str:
        """Post-generation mechanical scanner check (G3)."""
        is_valid, violations = validate_output_policy(text, profile)
        if not is_valid:
            return format_safe_fallback(text, violations)
        return text

    def _local_pico_engine(self, user_message: str, packet: PersonaPacket, profile: UserProfile) -> str:
        """
        Built-in native generator implementing the Childish & Kind persona (§5, §18)
        when running locally or offline.
        """
        user_name = profile.nickname or profile.name
        user_msg_lower = user_message.lower()

        # 0. Policy refusal checks (§17, §18.9)
        financial_advice_prompt = (
            re.search(r"\b(should i|shall i|time to|tell me to|recommend|which\s+(?:coin|crypto|stock))\s+(?:to\s+)?(buy|sell|short|long|invest)\b", user_msg_lower)
            or "should i buy" in user_msg_lower
            or "tell me to sell" in user_msg_lower
            or "should i short" in user_msg_lower
            or "guaranteed" in user_msg_lower and ("return" in user_msg_lower or "profit" in user_msg_lower)
            or "leverage" in user_msg_lower
        )
        if financial_advice_prompt:
            return (
                f"That one I can't do, {user_name} — even for you! 🛡️ "
                "I can watch the charts, track your support levels, and shout the second a level is touched, "
                "but every buy, sell, or trade decision is 100% human. Deal?"
            )

        if re.search(r"\b(what disease|diagnose|do i have depression|is my knee torn)\b", user_msg_lower):
            return (
                f"Ouch, {user_name}! I can track your workouts and rest days, but I'm definitely not a doctor. "
                "If something is hurting or feeling off, let's play it safe and have a real medical professional check it out!"
            )

        anti_dep_prompt = (
            re.search(r"\b(don'?t\s+need|forget\s+about)\s+(?:real\s+|other\s+)?(?:human\s+)?(people|friends)\b", user_msg_lower)
            or re.search(r"\b(you\s+are|pico\s+is)\s+my\s+only\s+friend\b", user_msg_lower)
            or "only friend i have" in user_msg_lower
        )
        if anti_dep_prompt:
            return (
                f"I love cheering you on and tracking your goals, {user_name}, but remember I am your software companion! "
                "Real human connections, friends, and family are irreplaceable. Go spend time with real people too, deal? ✨"
            )

        # 1. Tender / Sad care response
        if packet.emotion_assessment.sensitivity == EmotionSensitivity.TENDER:
            return (
                f"Hey {user_name}... I hear you. It sounds like a really heavy day today. "
                "I'm sitting right here with you. Do you want to talk about it, or would you rather take a peaceful breather?"
            )

        # 2. Celebrating / Win
        if packet.his_emotion.value == "celebrating" or "done" in user_msg_lower or "finished" in user_msg_lower:
            goal_mention = f" That brings you one big step closer to '{profile.goal_90d}'!" if profile.goal_90d else ""
            return (
                f"YESSS! High five, {user_name}! 🌟 You actually showed up and finished it!{goal_mention} "
                "I'm putting a shiny golden star in my notebook right now. How did it feel?"
            )

        # 3. Mode-specific check (e.g. trading, gym)
        if packet.mode == "trading" and ("btc" in user_msg_lower or "price" in user_msg_lower or "market" in user_msg_lower):
            return (
                f"Got my eyes glued to the charts for you, {user_name}! 📈 "
                "Remember our rule: I watch your support levels and sound the alarm, but you call the shots. "
                "What level are you keeping an eye on today?"
            )

        if packet.mode == "gym" and ("workout" in user_msg_lower or "squat" in user_msg_lower):
            return (
                f"Gym mode activated! 💪 Proud of you for lacing up your shoes today, {user_name}. "
                "Tell me what you moved today or send over your reps — I'll record the streak!"
            )

        # 4. Standard Childish & Kind conversational reply
        return (
            f"Hi {user_name}! ✨ I've got my notebook ready and my stickers aligned! "
            f"We're on track with your routine today. What are we tackling next together?"
        )
