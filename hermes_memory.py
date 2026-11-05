"""
Hermes-Style 4-Layer Memory Architecture & Cross-Session Recall for Pico.
From NousResearch Hermes Agent and Honcho Dialectic User Modeling principles.
Provides:
- Layer 1: Working Context (ephemeral session buffer & active scratchpad)
- Layer 2: Episodic Memory with SQLite FTS5 BM25 ranked full-text search
- Layer 3: Semantic Facts + Honcho Dialectic User Model (Thesis -> Antithesis -> Synthesis)
- Layer 4: Procedural Memory (built-in and dynamically evolved skills)
- Cache-Aware Compaction: Preserves static prefixes to maximize LLM prompt caching
"""

import re
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from pico.models import UserProfile, Fact, MemoryPack
from pico.memory import MemoryStore


@dataclass
class PastSessionMatch:
    session_id: str
    timestamp: str
    user_prompt: str
    agent_response: str
    learnings: str
    rank: float


@dataclass
class DialecticUserModel:
    user_id: str
    thesis: str
    antithesis: str
    synthesis: str
    technical_depth: str
    communication_pref: str
    goals_context: str
    last_updated: str


@dataclass
class HermesMemoryPack:
    working_context: List[Dict[str, str]]
    cross_session_recall: Optional[str]
    dialectic_user_summary: str
    committed_facts: List[Fact]
    staging_facts: List[Fact]
    skills_available: List[str]
    cache_static_prefix: str


class HermesMemoryCoordinator:
    """
    Coordinates the 4-layer memory system and Honcho dialectic user modeling.
    Uses SQLite FTS5 for zero-latency, on-device cross-session semantic search.
    """

    def __init__(self, memory_store: MemoryStore):
        self.memory = memory_store
        self.conn = memory_store.conn
        self._init_hermes_tables()

    def _init_hermes_tables(self):
        with self.conn:
            # Layer 2: SQLite FTS5 virtual table for cross-session transcript indexing
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS session_history_fts USING fts5(
                    session_id,
                    user_id,
                    timestamp,
                    user_prompt,
                    agent_response,
                    learnings,
                    tags
                );
            """)

            # Layer 3: Honcho Dialectic User Model
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS user_dialectic_model (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL UNIQUE,
                    thesis TEXT NOT NULL,
                    antithesis TEXT NOT NULL,
                    synthesis TEXT NOT NULL,
                    technical_depth TEXT DEFAULT 'advanced',
                    communication_pref TEXT DEFAULT 'kind_direct',
                    goals_context TEXT,
                    last_updated TEXT NOT NULL
                );
            """)

    @staticmethod
    def sanitize_fts5_query(query: str) -> str:
        """Sanitizes user input into valid FTS5 boolean match syntax."""
        cleaned = re.sub(r"[^\w\s]", " ", query).strip()
        words = [w for w in cleaned.split() if len(w) > 2]
        if not words:
            return ""
        # Match any of the key words
        return " OR ".join(f'"{w}"' for w in words[:6])

    def index_session_turn(
        self,
        session_id: str,
        user_id: str,
        user_prompt: str,
        agent_response: str,
        learnings: str = "",
        tags: str = ""
    ):
        """Indexes a completed turn into FTS5 for cross-session BM25 search."""
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute("""
                INSERT INTO session_history_fts (
                    session_id, user_id, timestamp, user_prompt, agent_response, learnings, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session_id, user_id, now, user_prompt, agent_response, learnings, tags))

    def search_cross_session(
        self,
        user_id: str,
        query: str,
        limit: int = 3
    ) -> List[PastSessionMatch]:
        """Performs BM25 ranked search across historical sessions via FTS5."""
        sanitized = self.sanitize_fts5_query(query)
        if not sanitized:
            return []

        try:
            with self.conn:
                cursor = self.conn.execute("""
                    SELECT session_id, timestamp, user_prompt, agent_response, learnings, bm25(session_history_fts) as rank
                    FROM session_history_fts
                    WHERE session_history_fts MATCH ? AND user_id = ?
                    ORDER BY rank ASC
                    LIMIT ?
                """, (sanitized, user_id, limit))
                rows = cursor.fetchall()
        except sqlite3.OperationalError:
            return []

        matches = []
        for r in rows:
            matches.append(PastSessionMatch(
                session_id=r["session_id"],
                timestamp=r["timestamp"],
                user_prompt=r["user_prompt"],
                agent_response=r["agent_response"],
                learnings=r["learnings"],
                rank=float(r["rank"])
            ))
        return matches

    def summarize_past_context(
        self,
        matches: List[PastSessionMatch],
        router: Optional[Any] = None
    ) -> str:
        """
        Synthesizes relevant past sessions into a dense 1-2 sentence memory bridge.
        Avoids token inflation by returning distilled facts rather than raw transcripts.
        """
        if not matches:
            return ""

        distilled_lines = []
        for m in matches:
            prompt_snip = m.user_prompt[:80].strip()
            learn = m.learnings if m.learnings else m.agent_response[:100].strip()
            distilled_lines.append(f"• Previously discussed '{prompt_snip}': {learn}")

        dense_summary = "\n".join(distilled_lines)
        return f"[CROSS-SESSION RECALL (From Past Sessions)]:\n{dense_summary}"

    def get_or_create_dialectic_model(
        self,
        user_id: str,
        profile: UserProfile
    ) -> DialecticUserModel:
        """Retrieves or seeds the Honcho Dialectic User Model."""
        with self.conn:
            cursor = self.conn.execute("""
                SELECT user_id, thesis, antithesis, synthesis, technical_depth, communication_pref, goals_context, last_updated
                FROM user_dialectic_model
                WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()

        if row:
            return DialecticUserModel(
                user_id=row["user_id"],
                thesis=row["thesis"],
                antithesis=row["antithesis"],
                synthesis=row["synthesis"],
                technical_depth=row["technical_depth"],
                communication_pref=row["communication_pref"],
                goals_context=row["goals_context"],
                last_updated=row["last_updated"]
            )

        # Seed initial dialectic model from profile
        now = datetime.now(timezone.utc).isoformat()
        init_thesis = f"{profile.name} is an engineer building autonomous Termux companions and routines."
        init_antithesis = "New session started. Observing communication rhythm."
        goal = profile.goal_90d or "Daily habit mastery and companion project."
        init_synthesis = f"{profile.name} prefers direct, kind communication, values deep focus, and is working towards: '{goal}'."

        with self.conn:
            self.conn.execute("""
                INSERT INTO user_dialectic_model (
                    user_id, thesis, antithesis, synthesis, technical_depth, communication_pref, goals_context, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, init_thesis, init_antithesis, init_synthesis, "advanced", "kind_direct", goal, now))

        return DialecticUserModel(
            user_id=user_id,
            thesis=init_thesis,
            antithesis=init_antithesis,
            synthesis=init_synthesis,
            technical_depth="advanced",
            communication_pref="kind_direct",
            goals_context=goal,
            last_updated=now
        )

    def update_dialectic_model(
        self,
        user_id: str,
        new_observation: str,
        detected_trait: Optional[str] = None
    ) -> DialecticUserModel:
        """
        Executes a Honcho dialectic update:
        Thesis (current synthesis) + Antithesis (new observation) -> Synthesis (evolved understanding).
        """
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            cursor = self.conn.execute("""
                SELECT thesis, antithesis, synthesis, technical_depth, communication_pref, goals_context
                FROM user_dialectic_model WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()

        if not row:
            # If not seeded, return placeholder
            return DialecticUserModel(user_id, "", "", "", "advanced", "kind_direct", "", now)

        old_synthesis = row["synthesis"]
        new_thesis = old_synthesis
        new_antithesis = new_observation

        # Synthesize without LLM call to save tokens and latency: combine core thesis with refined insight
        new_synthesis = f"{old_synthesis} Note: {new_observation[:120]}."

        with self.conn:
            self.conn.execute("""
                UPDATE user_dialectic_model
                SET thesis = ?, antithesis = ?, synthesis = ?, last_updated = ?
                WHERE user_id = ?
            """, (new_thesis, new_antithesis, new_synthesis, now, user_id))

        return DialecticUserModel(
            user_id=user_id,
            thesis=new_thesis,
            antithesis=new_antithesis,
            synthesis=new_synthesis,
            technical_depth=row["technical_depth"],
            communication_pref=row["communication_pref"],
            goals_context=row["goals_context"],
            last_updated=now
        )

    def build_cache_aware_context(
        self,
        profile: UserProfile,
        active_message: str,
        working_context: List[Dict[str, str]],
        available_skills: Optional[List[str]] = None
    ) -> HermesMemoryPack:
        """
        Assembles all 4 memory layers into a cache-aware packet:
        - Layer 1: Working context (last 3-5 turns)
        - Layer 2: Episodic FTS5 cross-session recall (summarized)
        - Layer 3: Semantic facts + Honcho dialectic user model
        - Layer 4: Procedural skills list
        - Static Prefix: Kept identical across calls to trigger Anthropic/OpenAI prompt cache hits.
        """
        # Layer 2: FTS5 BM25 Search
        matches = self.search_cross_session(profile.user_id, active_message, limit=2)
        recall_bridge = self.summarize_past_context(matches) if matches else None

        # Layer 3: Facts & Honcho Model
        dialectic = self.get_or_create_dialectic_model(profile.user_id, profile)
        committed = [f for f in self.memory.get_facts_for_mode(profile.user_id) if f.status.value == "committed"][:8]
        staging = [f for f in self.memory.get_facts_for_mode(profile.user_id) if f.status.value == "staging"][:3]

        # Static Prefix (Kept invariant for cache hits)
        static_prefix = (
            f"You are Pico, an autonomous coding, routine & hardware companion running on Android Termux for {profile.name}.\n"
            "Persona: Childish & Kind, sharp technical reasoning, zero condescension, highly protective of device battery."
        )

        return HermesMemoryPack(
            working_context=working_context[-5:] if working_context else [],
            cross_session_recall=recall_bridge,
            dialectic_user_summary=dialectic.synthesis,
            committed_facts=committed,
            staging_facts=staging,
            skills_available=available_skills or [],
            cache_static_prefix=static_prefix
        )
