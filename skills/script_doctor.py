"""
Built-in Script Doctor & Hook Reviewer Skill for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§19 Content Creation).
"""

import time
import re
from typing import Dict, Any, Optional
from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel


class ScriptDoctorSkill(BaseSkill):
    name = "script_doctor"
    description = "Analyzes short-form video scripts (Shorts/Reels) for word pacing, hook retention, and runtime."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "script_text": {"type": "string", "required": True},
        "target_seconds": {"type": "integer", "required": False, "default": 60}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        script = inputs.get("script_text", "").strip()
        target_s = inputs.get("target_seconds", 60)

        if not script:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error="Empty script provided."
            )

        words = script.split()
        word_count = len(words)

        # Average energetic speaking rate: 2.5 words per second (150 words / min)
        est_seconds = round(word_count / 2.5, 1)

        # Analyze hook (first 2-3 sentences or ~15 words)
        first_sentence = re.split(r"[.!?]", script)[0] if script else ""
        first_sentence_lower = first_sentence.lower()

        hook_score = 7
        critique = "Clean opening."

        # Deduct for throat-clearing ("hey guys", "in today's video", "so basically")
        if any(w in first_sentence_lower for w in ["hey guys", "in this video", "welcome back", "so today"]):
            hook_score -= 3
            critique = "Throat-clearing opening detected. Cut straight to the conflict or surprising fact!"
        elif any(w in first_sentence_lower for w in ["secret", "stop", "never", "why", "truth about", "how"]):
            hook_score += 2
            critique = "Strong curiosity hook! Jumps directly into the tension."

        hook_score = max(1, min(10, hook_score))

        # Pacing evaluation
        if est_seconds > target_s + 5:
            pacing_status = f"Too long (+{round(est_seconds - target_s, 1)}s over {target_s}s cap). Needs trimming."
            one_advice = f"Cut roughly {word_count - int(target_s * 2.5)} words to hit exactly {target_s}s."
        elif est_seconds < target_s - 15:
            pacing_status = f"Fast / Short ({est_seconds}s vs {target_s}s target)."
            one_advice = "Good for an ultra-snappy reel! Make sure the payoff lands clearly."
        else:
            pacing_status = f"Perfect timing (~{est_seconds}s for a {target_s}s video)."
            one_advice = "Timing is locked in. Focus on clear visual cuts every 2-3 seconds."

        output = {
            "word_count": word_count,
            "estimated_runtime_seconds": est_seconds,
            "target_seconds": target_s,
            "hook_first_line": first_sentence,
            "hook_score": f"{hook_score}/10",
            "hook_critique": critique,
            "pacing_status": pacing_status,
            "one_advice": one_advice
        }

        return SkillResult(
            success=True,
            skill_name=self.name,
            output=output,
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )
