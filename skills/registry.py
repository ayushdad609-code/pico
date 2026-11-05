"""
Skill Registry for Pico.
Manages built-in and dynamically created skills.
"""

from typing import Dict, Any, List, Optional
from .base_skill import BaseSkill, SkillResult
from .script_doctor import ScriptDoctorSkill
from .macro_calculator import MacroCalculatorSkill
from .food_lookup import FoodLookupSkill
from .flashcard_generator import FlashcardGeneratorSkill
from .pomodoro_planner import PomodoroPlannerSkill
from .level_calculator import LevelCalculatorSkill
from .runway_calculator import RunwayCalculatorSkill
from .packing_checklist import PackingChecklistSkill
from .browser_skill import BrowserSkill
from .device_skill import DeviceSkill
from .coding_tools import (
    ReadFileSkill,
    WriteFileSkill,
    EditFileSkill,
    RunBashCommandSkill,
    ListDirSkill,
    GrepSearchSkill
)


class SkillRegistry:
    def __init__(self):
        self.skills: Dict[str, BaseSkill] = {}
        self._register_default_skills()

    def _register_default_skills(self):
        # 1. Content Creation
        self.register_skill(ScriptDoctorSkill())
        # 2. Fitness & Macros
        self.register_skill(MacroCalculatorSkill())
        # 3. Indian Food & Nutrition Lookup
        self.register_skill(FoodLookupSkill())
        # 4. Active Recall Flashcard Generator
        self.register_skill(FlashcardGeneratorSkill())
        # 5. Pomodoro Focus Planner
        self.register_skill(PomodoroPlannerSkill())
        # 6. Technical Fibonacci & Pivot Level Calculator
        self.register_skill(LevelCalculatorSkill())
        # 7. Startup Runway & Burn Meter
        self.register_skill(RunwayCalculatorSkill())
        # 8. Smart Travel Packing Checklist
        self.register_skill(PackingChecklistSkill())
        # 9. Cloud Browser Agent (Hand #2)
        self.register_skill(BrowserSkill())
        # 10. Android Hardware & Device Sensors
        self.register_skill(DeviceSkill())
        # 11-16. Claude Code Filesystem & Terminal Primitives
        self.register_skill(ReadFileSkill())
        self.register_skill(WriteFileSkill())
        self.register_skill(EditFileSkill())
        self.register_skill(RunBashCommandSkill())
        self.register_skill(ListDirSkill())
        self.register_skill(GrepSearchSkill())

    def register_skill(self, skill: BaseSkill):
        self.skills[skill.name] = skill

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        return self.skills.get(name)

    def list_skills(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "permission_level": s.permission_level.value,
                "parameters": s.parameters_schema
            }
            for s in self.skills.values()
        ]

    def execute_skill(self, name: str, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        if name not in self.skills:
            return SkillResult(
                success=False,
                skill_name=name,
                output={},
                error=f"Skill '{name}' is not registered."
            )
        skill = self.skills[name]
        if not skill.validate_inputs(inputs):
            return SkillResult(
                success=False,
                skill_name=name,
                output={},
                error=f"Invalid or missing required inputs for skill '{name}'."
            )
        return skill.execute(inputs, context)
