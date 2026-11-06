"""
Token Metering, Low Power Friend & Lock In Mode for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§16 Tokens & Lock In Mode).
"""

from __future__ import annotations
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional, Tuple
from pico.paths import get_default_db_path


FREE_MONTHLY_TOKEN_QUOTA = 40_000_000   # 40M tokens/month free pool
PRO_MONTHLY_TOKEN_QUOTA = 500_000_000  # 500M tokens/month Pro tier
LOW_POWER_DAILY_DRIP = 300_000          # 300k daily drip keeps basic chat alive


@dataclass
class TokenAccount:
    user_id: str
    monthly_allowance: int = FREE_MONTHLY_TOKEN_QUOTA
    tokens_used: int = 0
    tier: str = "free"  # "free" or "pro_lock_in"
    lock_in_sessions_left: int = 3  # 3 free trial sessions/month for free tier
    deep_research_left: int = 10    # 10 deep research runs/month
    warning_50_sent: bool = False
    warning_80_sent: bool = False
    warning_95_sent: bool = False
    rollover_tokens: int = 0
    last_drip_date: Optional[str] = None

    @property
    def used_tokens(self) -> int:
        return self.tokens_used

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.monthly_allowance - self.tokens_used)

    @property
    def usage_percentage(self) -> float:
        if self.monthly_allowance <= 0:
            return 100.0
        return (self.tokens_used / self.monthly_allowance) * 100.0

    @property
    def is_low_power(self) -> bool:
        return self.tokens_remaining == 0


class TokenManager:
    """Manages persistent token accounting, low-power mode transitions, and Lock In mode."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or ":memory:"
        self.accounts: Dict[str, TokenAccount] = {}
        self._init_db()

    def _init_db(self):
        """Initializes SQLite persistence for token balances across daemon restarts."""
        try:
            conn = sqlite3.connect(self.db_path)
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS token_accounts (
                        user_id TEXT PRIMARY KEY,
                        monthly_allowance INTEGER,
                        tokens_used INTEGER,
                        tier TEXT,
                        lock_in_sessions_left INTEGER,
                        deep_research_left INTEGER,
                        warning_50_sent INTEGER,
                        warning_80_sent INTEGER,
                        warning_95_sent INTEGER,
                        rollover_tokens INTEGER,
                        last_drip_date TEXT
                    )
                """)
            conn.close()
        except Exception:
            pass

    def _save_account(self, acc: TokenAccount):
        """Persists account state to SQLite."""
        try:
            conn = sqlite3.connect(self.db_path)
            with conn:
                conn.execute("""
                    INSERT OR REPLACE INTO token_accounts (
                        user_id, monthly_allowance, tokens_used, tier,
                        lock_in_sessions_left, deep_research_left,
                        warning_50_sent, warning_80_sent, warning_95_sent,
                        rollover_tokens, last_drip_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    acc.user_id, acc.monthly_allowance, acc.tokens_used, acc.tier,
                    acc.lock_in_sessions_left, acc.deep_research_left,
                    int(acc.warning_50_sent), int(acc.warning_80_sent), int(acc.warning_95_sent),
                    acc.rollover_tokens, acc.last_drip_date
                ))
            conn.close()
        except Exception:
            pass

    def get_or_create_account(self, user_id: str, tier: str = "free") -> TokenAccount:
        if user_id in self.accounts:
            return self.accounts[user_id]

        # Try loading from database
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT monthly_allowance, tokens_used, tier, lock_in_sessions_left, deep_research_left, warning_50_sent, warning_80_sent, warning_95_sent, rollover_tokens, last_drip_date FROM token_accounts WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                acc = TokenAccount(
                    user_id=user_id,
                    monthly_allowance=row[0],
                    tokens_used=row[1],
                    tier=row[2],
                    lock_in_sessions_left=row[3],
                    deep_research_left=row[4],
                    warning_50_sent=bool(row[5]),
                    warning_80_sent=bool(row[6]),
                    warning_95_sent=bool(row[7]),
                    rollover_tokens=row[8],
                    last_drip_date=row[9]
                )
                self.accounts[user_id] = acc
                return acc
        except Exception:
            pass

        allowance = PRO_MONTHLY_TOKEN_QUOTA if tier == "pro_lock_in" else FREE_MONTHLY_TOKEN_QUOTA
        acc = TokenAccount(user_id=user_id, tier=tier, monthly_allowance=allowance)
        self.accounts[user_id] = acc
        self._save_account(acc)
        return acc

    def get_balance(self, user_id: str) -> TokenAccount:
        """Convenience alias for get_or_create_account."""
        return self.get_or_create_account(user_id)

    def record_usage(self, user_id: str, tokens: int, is_exempt: bool = False) -> Tuple[TokenAccount, Optional[str]]:
        """
        Deducts tokens from user allowance unless exempt.
        Exempt operations (§16): Heartbeats, watchers, crisis protocol, nightly self-reports.
        """
        acc = self.get_or_create_account(user_id)
        if is_exempt:
            return acc, None

        acc.tokens_used += tokens
        warning_msg = None

        # Check threshold warnings (calm cards, no guilt-upselling)
        pct = acc.usage_percentage
        if pct >= 95 and not acc.warning_95_sent:
            acc.warning_95_sent = True
            warning_msg = "Notice: You've used 95% of your monthly tokens. Low Power mode will keep basic chat and watchers running smoothly!"
        elif pct >= 80 and not acc.warning_80_sent:
            acc.warning_80_sent = True
            warning_msg = "Notice: 80% of your monthly token pool used."
        elif pct >= 50 and not acc.warning_50_sent:
            acc.warning_50_sent = True
            warning_msg = "Notice: Halfway through your monthly tokens."

        self._save_account(acc)
        return acc, warning_msg

    def apply_daily_drip(self, user_id: str) -> bool:
        """
        Applies §16 300k daily drip if user has hit Low Power mode (0 tokens remaining).
        Enables uninterrupted daily friendship without paywalls.
        """
        acc = self.get_or_create_account(user_id)
        today_str = date.today().isoformat()
        if acc.tokens_remaining == 0 and acc.last_drip_date != today_str:
            acc.monthly_allowance += LOW_POWER_DAILY_DRIP
            acc.last_drip_date = today_str
            self._save_account(acc)
            return True
        return False

    def apply_monthly_reset(self, user_id: str):
        """
        Applies §16 monthly reset with 25% rollover of unused tokens into the next month.
        """
        acc = self.get_or_create_account(user_id)
        leftover = max(0, acc.monthly_allowance - acc.tokens_used)
        rollover = int(leftover * 0.25)
        base_quota = PRO_MONTHLY_TOKEN_QUOTA if acc.tier == "pro_lock_in" else FREE_MONTHLY_TOKEN_QUOTA

        acc.monthly_allowance = base_quota + rollover
        acc.tokens_used = 0
        acc.rollover_tokens = rollover
        acc.warning_50_sent = False
        acc.warning_80_sent = False
        acc.warning_95_sent = False
        self._save_account(acc)

    @staticmethod
    def enter_lock_in_mode(account: TokenAccount) -> Tuple[bool, str]:
        """
        Engages Lock In Mode 🔒.
        Free users get 3 trial sessions/month. Pro has unlimited.
        """
        if account.tier == "pro_lock_in":
            return True, "Locked in. Headphones on. Give me the problem."

        if account.lock_in_sessions_left > 0:
            account.lock_in_sessions_left -= 1
            return True, f"Locked in. Headphones on. (Trial session started — {account.lock_in_sessions_left} left this month). Give me the problem."

        return False, "You've used your 3 free Lock In trial sessions this month! Basic chat and watchers remain 100% active."
