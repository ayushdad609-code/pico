"""
Built-in Startup Runway & Cash Burn Meter Skill for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§19 Startups & Business).
"""

import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel


class RunwayCalculatorSkill(BaseSkill):
    name = "runway_calculator"
    description = "Calculates startup or business financial runway in months and highlights cash-burn danger zones."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "cash_balance": {"type": "number", "required": True},
        "monthly_burn_rate": {"type": "number", "required": True},
        "currency_symbol": {"type": "string", "required": False, "default": "₹"}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        try:
            cash = float(inputs.get("cash_balance", 0.0))
            burn = float(inputs.get("monthly_burn_rate", 0.0))
            curr = inputs.get("currency_symbol", "₹")
        except (ValueError, TypeError):
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error="Invalid numerical value for cash balance or monthly burn rate."
            )

        if cash < 0:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error="Cash balance cannot be negative."
            )

        if burn <= 0:
            return SkillResult(
                success=True,
                skill_name=self.name,
                output={
                    "runway_months": "Infinite (Profitable or Zero Burn)",
                    "health_tier": "SUSTAINABLE",
                    "his_line": f"Zero net burn detected! You are default alive with {curr}{cash:,.2f} in the bank."
                }
            )

        runway_months = round(cash / burn, 1)

        # Estimate zero-cash date
        days_left = int(runway_months * 30.4)
        zero_date = (datetime.now(timezone.utc) + timedelta(days=days_left)).strftime("%b %Y")

        if runway_months < 6.0:
            health_tier = "CRITICAL (<6 months)"
            warning = "🚨 Red Alert: Less than 6 months of runway remaining. Fundraising or immediate revenue generation is urgent."
            his_line = f"Runway is {runway_months} months! We hit the danger zone in {zero_date}. Time to cut non-essential costs and ship paid features."
        elif runway_months < 12.0:
            health_tier = "MODERATE (6–12 months)"
            warning = "⚠️ Yellow Zone: Keep an eye on burn rate; start planning seed conversations 4 months before deadline."
            his_line = f"You have {runway_months} months of breathing room until {zero_date}. Steady pace, stay focused on shipping."
        else:
            health_tier = "HEALTHY (>12 months)"
            warning = "✅ Green Zone: Comfortable runway. Focus on deep product-market fit."
            his_line = f"Rock solid! {runway_months} months of runway ({curr}{cash:,.0f} balance). You have time to build things right."

        output = {
            "cash_balance": f"{curr}{cash:,.2f}",
            "monthly_burn_rate": f"{curr}{burn:,.2f}",
            "runway_months": runway_months,
            "estimated_zero_cash_date": zero_date,
            "health_tier": health_tier,
            "status_notice": warning,
            "his_line": his_line
        }

        return SkillResult(
            success=True,
            skill_name=self.name,
            output=output,
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )
