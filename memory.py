"""
Two-Tier Memory System & What-I-Know Store for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§9 Memory System, §11 BTW Engine).
"""

import sqlite3
import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from .models import Fact, FactStatus, FactSource, Sensitivity, MemoryPack, UserProfile


class MemoryStore:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        with self.conn:
            # Facts table with two-tier trust (staging vs committed)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    sensitivity TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    review_date TEXT,
                    expires_at TEXT
                )
            """)

            # BTW Gaps Registry
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_gaps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    priority INTEGER DEFAULT 1,
                    sensitivity TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'open',
                    created_at TEXT NOT NULL
                )
            """)

            # Episodic diary entries
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS episodic_diary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    mood TEXT,
                    mode TEXT
                )
            """)

    def store_fact(self, user_id: str, fact: Fact) -> int:
        """Store or update a fact in memory."""
        # Calculate expiration for staging facts (7 days)
        expires_at = fact.expires_at
        if fact.status == FactStatus.STAGING and not expires_at:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

        val_str = json.dumps(fact.value) if not isinstance(fact.value, str) else fact.value

        with self.conn:
            # Check if key already exists for this mode
            cursor = self.conn.execute(
                "SELECT id, status, source FROM facts WHERE user_id = ? AND key = ? AND mode = ?",
                (user_id, fact.key, fact.mode)
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing fact (newest user-said value wins)
                self.conn.execute("""
                    UPDATE facts
                    SET value = ?, source = ?, confidence = ?, sensitivity = ?, status = ?,
                        created_at = ?, expires_at = ?
                    WHERE id = ?
                """, (val_str, fact.source.value, fact.confidence, fact.sensitivity.value,
                      fact.status.value, fact.created_at, expires_at, existing["id"]))
                return existing["id"]
            else:
                cursor = self.conn.execute("""
                    INSERT INTO facts (user_id, key, value, source, confidence, sensitivity, mode, status, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, fact.key, val_str, fact.source.value, fact.confidence,
                      fact.sensitivity.value, fact.mode, fact.status.value, fact.created_at, expires_at))
                return cursor.lastrowid

    def commit_fact(self, user_id: str, key: str, mode: str = "shared"):
        """Promote a staging fact to committed status."""
        with self.conn:
            self.conn.execute("""
                UPDATE facts
                SET status = 'committed', expires_at = NULL
                WHERE user_id = ? AND key = ? AND mode = ?
            """, (user_id, key, mode))

    def get_facts_for_mode(self, user_id: str, mode: str = "chill") -> List[Fact]:
        """Load facts visible to this mode (shared + mode-specific). Purges expired staging facts."""
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            # Clean up expired staging facts
            self.conn.execute("DELETE FROM facts WHERE user_id = ? AND expires_at IS NOT NULL AND expires_at < ?", (user_id, now))

            cursor = self.conn.execute("""
                SELECT key, value, source, confidence, sensitivity, mode, status, created_at, review_date, expires_at
                FROM facts
                WHERE user_id = ? AND (mode = 'shared' OR mode = ?)
                ORDER BY status DESC, created_at DESC
            """, (user_id, mode))
            rows = cursor.fetchall()

        facts = []
        for r in rows:
            raw_val = r["value"]
            try:
                val = json.loads(raw_val)
            except Exception:
                val = raw_val

            facts.append(Fact(
                key=r["key"],
                value=val,
                source=FactSource(r["source"]),
                confidence=r["confidence"],
                sensitivity=Sensitivity(r["sensitivity"]),
                mode=r["mode"],
                status=FactStatus(r["status"]),
                created_at=r["created_at"],
                review_date=r["review_date"],
                expires_at=r["expires_at"]
            ))
        return facts

    def build_memory_pack(self, profile: UserProfile, mode: str = "chill") -> MemoryPack:
        """Construct the MemoryPack for a run (§10 Step 3)."""
        all_facts = self.get_facts_for_mode(profile.user_id, mode)
        committed = [f for f in all_facts if f.status == FactStatus.COMMITTED][:15]
        staging = [f for f in all_facts if f.status == FactStatus.STAGING][:5]

        # Add profile baseline facts to committed if not present
        routine = {
            "wake": profile.wake_time,
            "sleep": profile.sleep_time,
            "timezone": profile.timezone
        }
        goals = []
        if profile.goal_90d:
            goals.append({"title": "90-Day Goal", "description": profile.goal_90d})

        preferences = {
            "languages": profile.languages,
            "funny_angry": profile.funny_angry_opt_in,
            "nudge_budget": profile.nudge_budget
        }

        # Query open gaps
        with self.conn:
            cursor = self.conn.execute(
                "SELECT fact_key FROM memory_gaps WHERE user_id = ? AND status = 'open' LIMIT 3",
                (profile.user_id,)
            )
            missing = [row["fact_key"] for row in cursor.fetchall()]

        return MemoryPack(
            committed_facts=committed,
            staging_facts=staging,
            routine=routine,
            goals=goals,
            preferences=preferences,
            missing=missing
        )

    def get_facts(self, user_id: str, mode: str = "chill") -> Dict[str, Any]:
        """Convenience method returning key-value dict of all facts accessible in this mode."""
        facts = self.get_facts_for_mode(user_id, mode)
        return {f.key: f.value for f in facts}

    # What-I-Know-About-You API (§9)
    def get_what_i_know(self, user_id: str) -> List[Dict[str, Any]]:
        """Returns every fact with source and status for user inspection/editing."""
        with self.conn:
            cursor = self.conn.execute("""
                SELECT id, key, value, source, sensitivity, mode, status, created_at
                FROM facts WHERE user_id = ? ORDER BY created_at DESC
            """, (user_id,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def delete_fact(self, user_id: str, fact_id: int) -> bool:
        """Real deletion across stores (§9)."""
        with self.conn:
            cursor = self.conn.execute("DELETE FROM facts WHERE user_id = ? AND id = ?", (user_id, fact_id))
            return cursor.rowcount > 0

    def register_gap(self, user_id: str, topic: str, fact_key: str, sensitivity: Sensitivity = Sensitivity.PERSONAL):
        """Register a wished-for fact into BTW Gaps (§11)."""
        with self.conn:
            self.conn.execute("""
                INSERT INTO memory_gaps (user_id, topic, fact_key, sensitivity, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, topic, fact_key, sensitivity.value, datetime.now(timezone.utc).isoformat()))
