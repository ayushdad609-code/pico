"""
Built-in Fibonacci & Pivot Support/Resistance Calculator Skill for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§17 Money Guardrails & §19.5 Trading).
Strict Policy: Mathematical numbers only. ZERO buy/sell/trade advice (SEBI compliant).
"""

import time
from typing import Dict, Any, Optional
from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel


class LevelCalculatorSkill(BaseSkill):
    name = "level_calculator"
    description = "Calculates technical Fibonacci retracement levels and pivot points from High, Low, and Close."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "high": {"type": "number", "required": True},
        "low": {"type": "number", "required": True},
        "close": {"type": "number", "required": False}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        try:
            high = float(inputs.get("high", 0.0))
            low = float(inputs.get("low", 0.0))
            close = float(inputs.get("close", high))
        except (ValueError, TypeError):
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error="Invalid numerical prices provided for high, low, or close."
            )

        if high <= low or high <= 0 or low <= 0:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error="High price must be strictly greater than low price and positive."
            )

        diff = high - low

        # Fibonacci Retracements (measured from low to high)
        fib_levels = {
            "fib_0_236": round(high - 0.236 * diff, 2),
            "fib_0_382": round(high - 0.382 * diff, 2),
            "fib_0_500": round(high - 0.500 * diff, 2),
            "fib_0_618_golden": round(high - 0.618 * diff, 2),
            "fib_0_786": round(high - 0.786 * diff, 2)
        }

        # Classic Floor Pivot Points
        pp = round((high + low + close) / 3.0, 2)
        r1 = round((2.0 * pp) - low, 2)
        r2 = round(pp + diff, 2)
        s1 = round((2.0 * pp) - high, 2)
        s2 = round(pp - diff, 2)

        output = {
            "input_range": {"high": high, "low": low, "close": close, "range_delta": round(diff, 2)},
            "fibonacci_retracements": fib_levels,
            "pivot_points": {
                "resistance_2": r2,
                "resistance_1": r1,
                "pivot_point": pp,
                "support_1": s1,
                "support_2": s2
            },
            "compliance_notice": "Pure mathematical calculation. Not investment advice. Every trade decision is 100% human.",
            "his_line": f"Computed your levels! Golden pocket sits at {fib_levels['fib_0_618_golden']} and central pivot is {pp}. I'll shout if price crosses your alert level!"
        }

        return SkillResult(
            success=True,
            skill_name=self.name,
            output=output,
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )
