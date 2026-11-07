"""
Outbound Telephony & Voice Agent Skill for Pico.
Handles contact resolution, Ask-First briefings, and initiating guarded phone calls via device SIM.
"""

import time
import asyncio
import concurrent.futures
from typing import Dict, Any, Optional

from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel
from telephony.contact_resolver import resolve_callee, CalleeInfo
from telephony.briefing import AuthorityLevel, FactsPacket, build_briefing_card
from telephony.call_session import CallSession
from device_sensors import SafeCommandRunner

class TelephonySkill(BaseSkill):
    name = "telephony_skill"
    description = "Resolves contacts, prepares pre-call briefings, and triggers native SIM phone calls."
    version = "v1.0"
    permission_level = PermissionLevel.ASK
    parameters_schema = {
        "action": {
            "type": "string",
            "required": True,
            "description": "One of: 'resolve', 'brief', 'dial'"
        },
        "target": {
            "type": "string",
            "required": False,
            "description": "Contact name or phone number"
        },
        "objective": {
            "type": "string",
            "required": False,
            "description": "Purpose and message of the call"
        },
        "authority": {
            "type": "string",
            "required": False,
            "description": "Authority level: 'L0', 'L1', 'L2', 'L3'"
        }
    }

    def _run_async(self, coro):
        """Safely execute an async coroutine from sync context without event loop conflicts."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return asyncio.run(coro)

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        action = inputs.get("action", "resolve").lower()
        target = inputs.get("target", "").strip()
        objective = inputs.get("objective", "Deliver message").strip()

        try:
            if action == "resolve":
                if not target:
                    return SkillResult(
                        success=False,
                        skill_name=self.name,
                        output=None,
                        error="Target contact or phone number required.",
                        execution_time_ms=round((time.time() - start_t) * 1000, 2)
                    )
                callee = self._run_async(resolve_callee(target))
                if not callee:
                    return SkillResult(
                        success=False,
                        skill_name=self.name,
                        output=None,
                        error=f"Could not find contact '{target}'.",
                        execution_time_ms=round((time.time() - start_t) * 1000, 2)
                    )
                return SkillResult(
                    success=True,
                    skill_name=self.name,
                    output=callee.to_dict(),
                    execution_time_ms=round((time.time() - start_t) * 1000, 2)
                )

            elif action == "brief":
                if not target:
                    return SkillResult(
                        success=False,
                        skill_name=self.name,
                        output=None,
                        error="Target contact or phone number required.",
                        execution_time_ms=round((time.time() - start_t) * 1000, 2)
                    )
                callee = self._run_async(resolve_callee(target))
                if not callee:
                    return SkillResult(
                        success=False,
                        skill_name=self.name,
                        output=None,
                        error=f"Could not find contact '{target}'.",
                        execution_time_ms=round((time.time() - start_t) * 1000, 2)
                    )
                
                auth_str = inputs.get("authority", "L0").upper()
                authority = {
                    "L0": AuthorityLevel.L0,
                    "L1": AuthorityLevel.L1,
                    "L2": AuthorityLevel.L2,
                    "L3": AuthorityLevel.L3
                }.get(auth_str, AuthorityLevel.L0)

                packet = FactsPacket(
                    callee=callee,
                    objective=objective,
                    authority=authority,
                    allowlist_confirmed=True
                )
                card = build_briefing_card(packet)
                return SkillResult(
                    success=True,
                    skill_name=self.name,
                    output=card,
                    execution_time_ms=round((time.time() - start_t) * 1000, 2)
                )

            elif action == "dial":
                phone_number = inputs.get("phone_number", target)
                if not phone_number:
                    return SkillResult(
                        success=False,
                        skill_name=self.name,
                        output=None,
                        error="Phone number required for dial.",
                        execution_time_ms=round((time.time() - start_t) * 1000, 2)
                    )
                
                ok, out, err = self._run_async(SafeCommandRunner.run(["termux-telephony-call", phone_number], timeout=2.0))
                if not ok:
                    return SkillResult(
                        success=False,
                        skill_name=self.name,
                        output=None,
                        error=f"Failed to initiate call: {err}",
                        execution_time_ms=round((time.time() - start_t) * 1000, 2)
                    )
                return SkillResult(
                    success=True,
                    skill_name=self.name,
                    output={"dialed": phone_number, "status": "initiated"},
                    execution_time_ms=round((time.time() - start_t) * 1000, 2)
                )

            else:
                return SkillResult(
                    success=False,
                    skill_name=self.name,
                    output=None,
                    error=f"Unknown action: {action}",
                    execution_time_ms=round((time.time() - start_t) * 1000, 2)
                )

        except Exception as e:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output=None,
                error=str(e),
                execution_time_ms=round((time.time() - start_t) * 1000, 2)
            )
