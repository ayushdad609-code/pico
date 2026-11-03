"""
Built-in Pomodoro Deep Work Flow Planner Skill for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§1 Routine & §19 Study/Coding).
"""

import time
from typing import Dict, Any, Optional, List
from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel


class PomodoroPlannerSkill(BaseSkill):
    name = "pomodoro_planner"
    description = "Schedules structured Pomodoro focus and recovery intervals (25/5 or 50/10) with burnout prevention."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "available_hours": {"type": "number", "required": True},
        "mode_preference": {"type": "string", "required": False, "default": "standard_25"},  # standard_25 or ultradian_50
        "task_name": {"type": "string", "required": False, "default": "Focus Session"}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        hours = float(inputs.get("available_hours", 2.0))
        pref = inputs.get("mode_preference", "standard_25")
        task = inputs.get("task_name", "Focus Session")

        if hours <= 0:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error="Available hours must be greater than zero."
            )

        total_mins = int(hours * 60)
        work_len = 50 if pref == "ultradian_50" else 25
        short_break = 10 if pref == "ultradian_50" else 5
        cycle_len = work_len + short_break

        num_cycles = max(1, total_mins // cycle_len)
        actual_focus_mins = num_cycles * work_len
        actual_break_mins = total_mins - actual_focus_mins

        timeline: List[str] = []
        current_minute = 0
        for i in range(1, num_cycles + 1):
            w_start = current_minute
            w_end = w_start + work_len
            timeline.append(f"Block #{i} (Min {w_start}–{w_end}): Focus sprint on '{task}' ({work_len} mins)")
            current_minute = w_end

            if i % 4 == 0 and i < num_cycles:
                timeline.append(f"🌟 Extended Recovery (Min {current_minute}–{current_minute + 15}): Stand up, hydrate, walk around (15 mins)")
                current_minute += 15
            elif i < num_cycles:
                timeline.append(f"Rest (Min {current_minute}–{current_minute + short_break}): Quick screen-off breath ({short_break} mins)")
                current_minute += short_break

        # Burnout guardrail
        burnout_warning = None
        if hours >= 4.5:
            burnout_warning = "⚠️ Over 4 hours of deep study planned. Make sure to schedule an actual meal and fresh-air break!"

        output = {
            "task": task,
            "total_window_hours": hours,
            "focus_cycles": num_cycles,
            "cycle_type": f"{work_len} min focus / {short_break} min rest",
            "total_focus_time_mins": actual_focus_mins,
            "total_rest_time_mins": actual_break_mins,
            "timeline": timeline,
            "burnout_warning": burnout_warning,
            "his_line": f"Mapped {num_cycles} clean focus cycles ({actual_focus_mins} mins pure focus)! Put your phone in the other room and let's conquer this block."
        }

        return SkillResult(
            success=True,
            skill_name=self.name,
            output=output,
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )
