"""
Outbound Telephony & Voice Agent Skill for Pico.
Handles contact resolution, Ask-First briefings, and initiating guarded phone calls via device SIM.
"""

import time
import asyncio
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

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        action = inputs.get("action", "resolve").lower()
        target = inputs.get("target", "").strip()
        objective = inputs.get("objective", "Deliver message").strip()

        try:
            if action == "resolve":
                if not target:
                    return SkillResult(success=False, error="Target contact or phone number required.", execution_time_s=time.time() - start_t)
                # Run resolve_callee
                callee = asyncio.run(resolve_callee(target))
                if not callee:
                    return SkillResult(success=False, error=f"Could not find contact '{target}'.", execution_time_s=time.time() - start_t)
                return SkillResult(success=True, data=callee.to_dict(), execution_time_s=time.time() - start_t)

            elif action == "brief":
                if not target:
                    return SkillResult(success=False, error="Target contact or phone number required.", execution_time_s=time.time() - start_t)
                callee = asyncio.run(resolve_callee(target))
                if not callee:
                    return SkillResult(success=False, error=f"Could not find contact '{target}'.", execution_time_s=time.time() - start_t)
                
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
                return SkillResult(success=True, data=card, execution_time_s=time.time() - start_t)

            elif action == "dial":
                phone_number = inputs.get("phone_number", target)
                if not phone_number:
                    return SkillResult(success=False, error="Phone number required for dial.", execution_time_s=time.time() - start_t)
                
                # Native call execution via termux-telephony-call
                ok, out, err = asyncio.run(SafeCommandRunner.run(["termux-telephony-call", phone_number], timeout=2.0))
                if not ok:
                    return SkillResult(success=False, error=f"Failed to initiate call: {err}", execution_time_s=time.time() - start_t)
                return SkillResult(success=True, data={"dialed": phone_number, "status": "initiated"}, execution_time_s=time.time() - start_t)

            else:
                return SkillResult(success=False, error=f"Unknown action: {action}", execution_time_s=time.time() - start_t)

        except Exception as e:
            return SkillResult(success=False, error=str(e), execution_time_s=time.time() - start_t)
