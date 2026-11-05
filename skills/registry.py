"""
Skill Registry for Pico.
Manages built-in and dynamically created skills.
"""

import os
import glob
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
    _shared_instance: Optional["SkillRegistry"] = None

    def __init__(self):
        self.skills: Dict[str, BaseSkill] = {}
        self._register_default_skills()
        SkillRegistry._shared_instance = self

    @classmethod
    def get_shared_instance(cls) -> "SkillRegistry":
        if cls._shared_instance is None:
            cls._shared_instance = SkillRegistry()
        return cls._shared_instance

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
        # 17. Hermes Skill Self-Improvement Engine (6 actions)
        from .skill_manage import SkillManageSkill
        self.register_skill(SkillManageSkill(registry=self))
        # 18. Load any custom skills from disk
        self.load_custom_skills()

    def load_custom_skills(self, custom_dir: Optional[str] = None):
        """Scans custom skills directory and registers all active custom skills."""
        from .skill_manage import SkillManageSkill, CUSTOM_SKILLS_DIR
        target_dir = custom_dir or CUSTOM_SKILLS_DIR
        if not os.path.exists(target_dir):
            return

        for filepath in glob.glob(os.path.join(target_dir, "*.py")):
            basename = os.path.basename(filepath)
            if basename.startswith("__") or basename.endswith(".bak"):
                continue
            skill_name = basename[:-3]
            try:
                skill = SkillManageSkill.load_skill_from_file(filepath, skill_name)
                if skill:
                    self.register_skill(skill)
            except Exception:
                pass

    def register_skill(self, skill: BaseSkill):
        self.skills[skill.name] = skill

    def unregister_skill(self, name: str) -> bool:
        """Removes a skill from active registry."""
        if name in self.skills:
            del self.skills[name]
            return True
        return False

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
