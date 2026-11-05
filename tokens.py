"""
Token Metering, Low Power Friend & Lock In Mode for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§16 Tokens & Lock In Mode).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple


FREE_MONTHLY_TOKEN_QUOTA = 40_000_000  # 40M tokens/month free pool
LOW_POWER_DAILY_DRIP = 300_000         # 300k daily drip keeps basic chat alive


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

    @property
    def used_tokens(self) -> int:
        return self.tokens_used

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.monthly_allowance - self.tokens_used)

    @property
    def usage_percentage(self) -> float:
        return (self.tokens_used / self.monthly_allowance) * 100.0

    @property
    def is_low_power(self) -> bool:
        return self.tokens_remaining == 0


class TokenManager:
    """Manages token accounting, low-power mode transitions, and Lock In mode."""

    def __init__(self):
        self.accounts: Dict[str, TokenAccount] = {}

    def get_or_create_account(self, user_id: str, tier: str = "free") -> TokenAccount:
        if user_id not in self.accounts:
            self.accounts[user_id] = TokenAccount(user_id=user_id, tier=tier)
        return self.accounts[user_id]

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
            warning_msg = "Notice: You've used 95% of your free monthly tokens. Low Power mode will keep basic chat and watchers running smoothly!"
        elif pct >= 80 and not acc.warning_80_sent:
            acc.warning_80_sent = True
            warning_msg = "Notice: 80% of your monthly token pool used."
        elif pct >= 50 and not acc.warning_50_sent:
            acc.warning_50_sent = True
            warning_msg = "Notice: Halfway through your monthly tokens."

        return acc, warning_msg

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
