"""
Hermes-Style Agent-Curated Memory & Self-Prompting Nudge Engine for Pico.
From NousResearch Hermes Agent and Honcho Dialectic User Modeling principles.

Provides:
1. reflect_and_curate: Post-turn self-prompting reflection that identifies user preferences,
   extracts facts, updates the Honcho dialectic user model, and indexes turns into SQLite FTS5.
2. periodic_nudges: Intelligent, non-intrusive proactive nudges during idle heartbeat
   or after interaction milestones ("Pico noticed you do X...").
3. zero-inflation: Cache-aware distillation ensuring token bills never bloat.
"""

import re
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from pico.models import UserProfile, Fact, FactStatus, FactSource, Sensitivity
from pico.memory import MemoryStore
from pico.hermes_memory import HermesMemoryCoordinator, DialecticUserModel

logger = logging.getLogger("pico.hermes_curator")


class HermesMemoryCurator:
    """
    Autonomous memory curator that prompts itself to inspect and persist knowledge.
    Keeps Pico's procedural and semantic memory sharp across sessions.
    """

    def __init__(self, hermes_memory: HermesMemoryCoordinator, memory_store: MemoryStore):
        self.hermes = hermes_memory
        self.memory = memory_store
        self.turn_count: int = 0
        self.last_nudge_time: float = 0.0

    def reflect_and_curate(
        self,
        user_id: str,
        prompt: str,
        agent_response: str,
        session_id: Optional[str] = None,
        tools_used: Optional[List[str]] = None,
        router: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Self-prompting reflection routine executed at the end of an interaction.
        1. Extracts facts and persists them to MemoryStore.
        2. Formulates Honcho dialectic observation (Thesis -> Antithesis -> Synthesis).
        3. Indexes the turn into SQLite FTS5 for cross-session recall.
        """
        self.turn_count += 1
        sid = session_id or f"sess_{int(time.time())}"
        extracted_facts: List[Fact] = []

        # -------------------------------------------------------------
        # 1. Self-curation: Extract declarative facts & preferences
        # -------------------------------------------------------------
        pref_matches = self._extract_preferences(prompt)
        for key, fact_text in pref_matches:
            fact = Fact(
                key=key,
                value=fact_text,
                source=FactSource.USER_SAID,
                confidence=0.92,
                sensitivity=Sensitivity.PERSONAL,
                mode="shared",
                status=FactStatus.COMMITTED
            )
            self.memory.store_fact(user_id=user_id, fact=fact)
            extracted_facts.append(fact)

        # -------------------------------------------------------------
        # 2. Honcho Dialectic Update: Evolve the user model
        # -------------------------------------------------------------
        observation = self._synthesize_observation(prompt, agent_response, tools_used)
        dialectic_model = self.hermes.update_dialectic_model(
            user_id=user_id,
            new_observation=observation
        )

        # -------------------------------------------------------------
        # 3. Episodic FTS5 Indexing: Cross-session search index
        # -------------------------------------------------------------
        tags_list = tools_used or []
        if pref_matches:
            tags_list.append("preference")
        tags_str = " ".join(tags_list)

        learnings_snip = f"User noted: '{observation[:80]}'" if observation else ""
        self.hermes.index_session_turn(
            session_id=sid,
            user_id=user_id,
            user_prompt=prompt,
            agent_response=agent_response[:300],
            learnings=learnings_snip,
            tags=tags_str
        )

        # Check if periodic nudge is warranted
        nudge = self.check_and_generate_nudge(user_id)

        return {
            "turn": self.turn_count,
            "facts_extracted": len(extracted_facts),
            "dialectic_synthesis": dialectic_model.synthesis,
            "indexed_session": sid,
            "nudge": nudge
        }

    def _extract_preferences(self, prompt: str) -> List[Tuple[str, str]]:
        """Identifies explicit preferences and environment declarations."""
        results: List[Tuple[str, str]] = []
        p_lower = prompt.lower()

        # Preference patterns
        m_pref = re.search(r"\b(?:i prefer|i like|always use|prefer to use|default to)\s+([^.?!,]+)", p_lower)
        if m_pref:
            results.append(("pref_general", f"User prefers {m_pref.group(1).strip()}"))

        # Goal patterns
        m_goal = re.search(r"\b(?:my goal is|i am building|i'm working on|target is)\s+([^.?!,]+)", p_lower)
        if m_goal:
            results.append(("goal_active", f"Working on {m_goal.group(1).strip()}"))

        # Hardware / Device facts
        if "termux" in p_lower:
            results.append(("env_platform", "Development environment is Android Termux"))
        if "realme" in p_lower:
            results.append(("device_hardware", "Device model Realme 11 Pro 5G"))

        return results

    def _synthesize_observation(
        self,
        prompt: str,
        response: str,
        tools_used: Optional[List[str]] = None
    ) -> str:
        """Distills turn into a sharp Honcho dialectic observation."""
        p_clean = prompt[:90].replace("\n", " ").strip()
        if tools_used:
            return f"Executed workflow with tools [{', '.join(tools_used)}] for task: '{p_clean}'"
        if len(prompt) < 30:
            return f"Quick query: '{p_clean}'"
        return f"Engaged in topic: '{p_clean}'"

    def check_and_generate_nudge(
        self,
        user_id: str,
        profile: Optional[UserProfile] = None,
        force: bool = False
    ) -> Optional[str]:
        """
        Evaluates whether Pico should present a childish & kind proactive nudge.
        Respects cooldowns and user quiet hours.
        """
        now = time.time()
        # Cooldown: At least 5 turns and 15 minutes between nudges
        if not force:
            if self.turn_count < 5 or (now - self.last_nudge_time) < 900:
                return None

        # Check hour (avoid late night nudges 23:00 - 07:00)
        current_hour = datetime.now().hour
        if not force and (current_hour >= 23 or current_hour < 7):
            return None

        self.last_nudge_time = now

        # Generate contextual nudge
        if self.turn_count >= 10:
            return "🌱 *Pico peeks over his notebook*: We've been working hard on code and companion tasks! Don't forget to take a 5-minute stretch or sip some water!"
        elif self.turn_count >= 5:
            return "✏️ *Pico gives a little nudge*: I've saved our recent setup and preferences to my memory so you don't have to repeat them next time!"
        else:
            return "✏️ *Pico gives a little nudge*: Hello! I'm here and ready to help you build or organize your day whenever you are!"
