"""
The Receipts Timeline Engine for Pico (Feature F1).
Enforces the "Measured Truth" wedge: every verdict, recommendation, and market/sensor
claim carries a tap-to-verify evidence receipt.
"""

from __future__ import annotations
import sqlite3
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import List, Dict, Any, Optional
from pico.paths import get_default_db_path


@dataclass
class Receipt:
    id: str
    user_id: str
    claim: str
    source_type: str  # "memory_fact", "market_price", "sensor_reading", "web_fetch", "routine_spine"
    source_ref: str   # e.g., "fact:protein_style", "binance:BTCUSDT", "statvfs:storage", "url:..."
    timestamp: str
    value_recorded: str
    verified: bool = True
    user_correction: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "claim": self.claim,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "timestamp": self.timestamp,
            "value_recorded": self.value_recorded,
            "verified": self.verified,
            "user_correction": self.user_correction
        }


class ReceiptsTimelineEngine:
    """Manages the Receipts Timeline across user interactions."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_default_db_path()
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS receipts_timeline (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        claim TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        source_ref TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        value_recorded TEXT NOT NULL,
                        verified INTEGER DEFAULT 1,
                        user_correction TEXT
                    )
                """)
            conn.close()
        except Exception:
            pass

    def record_receipt(
        self,
        user_id: str,
        claim: str,
        source_type: str,
        source_ref: str,
        value_recorded: Any
    ) -> Receipt:
        """Records an auditable evidence receipt for a claim or verdict."""
        r_id = f"rcpt_{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        val_str = json.dumps(value_recorded) if not isinstance(value_recorded, str) else value_recorded

        receipt = Receipt(
            id=r_id,
            user_id=user_id,
            claim=claim,
            source_type=source_type,
            source_ref=source_ref,
            timestamp=now_iso,
            value_recorded=val_str
        )

        try:
            conn = sqlite3.connect(self.db_path)
            with conn:
                conn.execute("""
                    INSERT INTO receipts_timeline (
                        id, user_id, claim, source_type, source_ref, timestamp, value_recorded, verified, user_correction
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    receipt.id, receipt.user_id, receipt.claim, receipt.source_type,
                    receipt.source_ref, receipt.timestamp, receipt.value_recorded,
                    1, None
                ))
            conn.close()
        except Exception:
            pass

        return receipt

    def get_timeline(self, user_id: str, limit: int = 50) -> List[Receipt]:
        """Fetches the chronological receipts timeline for the user."""
        receipts = []
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, claim, source_type, source_ref, timestamp, value_recorded, verified, user_correction
                FROM receipts_timeline WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?
            """, (user_id, limit))
            for r in cursor.fetchall():
                receipts.append(Receipt(
                    id=r[0],
                    user_id=r[1],
                    claim=r[2],
                    source_type=r[3],
                    source_ref=r[4],
                    timestamp=r[5],
                    value_recorded=r[6],
                    verified=bool(r[7]),
                    user_correction=r[8]
                ))
            conn.close()
        except Exception:
            pass
        return receipts

    def correct_receipt(self, receipt_id: str, correction: str) -> Optional[Receipt]:
        """Allows user to correct a receipt; updates status and records correction."""
        try:
            conn = sqlite3.connect(self.db_path)
            with conn:
                conn.execute("""
                    UPDATE receipts_timeline
                    SET user_correction = ?, verified = 0
                    WHERE id = ?
                """, (correction, receipt_id))
            conn.close()
        except Exception:
            pass

        # Return updated record
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, claim, source_type, source_ref, timestamp, value_recorded, verified, user_correction
                FROM receipts_timeline WHERE id = ?
            """, (receipt_id,))
            r = cursor.fetchone()
            conn.close()
            if r:
                return Receipt(
                    id=r[0], user_id=r[1], claim=r[2], source_type=r[3],
                    source_ref=r[4], timestamp=r[5], value_recorded=r[6],
                    verified=bool(r[7]), user_correction=r[8]
                )
        except Exception:
            pass
        return None
