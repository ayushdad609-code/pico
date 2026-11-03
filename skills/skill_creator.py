"""
Dynamic Skill Creator Engine for Pico.
Allows Pico or the developer to define, validate, test, and register new skills on the fly.
From YOUR_FRIEND_FULL_SETUP.pdf (§12 Hands & Extensions).
"""

import re
import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, Callable
from .base_skill import BaseSkill, SkillResult
from .registry import SkillRegistry
from pico.mcp_host import PermissionLevel


# Dangerous operations forbidden inside dynamically created skills
DISALLOWED_PATTERNS = [
    re.compile(r"\b(rm\s+-rf|format\s+[a-z]:|os\.system\(|subprocess\.call\()\b", re.IGNORECASE),
    re.compile(r"\b(withdraw|transfer[_\s]funds|send[_\s]payment)\b", re.IGNORECASE),
    re.compile(r"__import__\(['\"]os['\"]\)\.system", re.IGNORECASE),
]


@dataclass
class SkillSpec:
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    logic_callable: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    python_code: Optional[str] = None
    permission_level: PermissionLevel = PermissionLevel.SEE
    version: str = "v1.0"


class DynamicSkill(BaseSkill):
    """A skill created dynamically at runtime by the Skill Creator."""
    def __init__(self, spec: SkillSpec):
        self.name = spec.name
        self.description = spec.description
        self.version = spec.version
        self.permission_level = spec.permission_level
        self.parameters_schema = spec.parameters_schema
        self._logic = spec.logic_callable

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        try:
            if not self._logic:
                return SkillResult(
                    success=False,
                    skill_name=self.name,
                    output={},
                    error="No execution logic defined for dynamic skill."
                )
            result = self._logic(inputs)
            return SkillResult(
                success=True,
                skill_name=self.name,
                output=result
            )
        except Exception as e:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error=f"Error executing dynamic skill: {str(e)}"
            )


class SkillCreator:
    """
    Validates, dry-tests, and saves newly generated skills.
    """
    def __init__(self, registry: Optional[SkillRegistry] = None):
        self.registry = registry or SkillRegistry()

    def validate_spec(self, spec: SkillSpec) -> Tuple[bool, Optional[str]]:
        """Scans skill specification for naming conventions and safety policies."""
        if not re.match(r"^[a-z][a-z0-9_]{2,30}$", spec.name):
            return False, "Skill name must be lowercase alphanumeric with underscores (3-30 chars)."

        if spec.python_code:
            for pat in DISALLOWED_PATTERNS:
                if pat.search(spec.python_code):
                    return False, f"Skill code rejected by safety policy: contains forbidden pattern '{pat.pattern}'."

        return True, None

    def create_and_register_skill(
        self,
        spec: SkillSpec,
        dry_run_input: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Optional[BaseSkill]]:
        """
        Creates, dry-tests, and registers the new skill into Pico's registry.
        """
        # 1. Safety validation
        is_valid, error = self.validate_spec(spec)
        if not is_valid:
            return False, f"Validation Failed: {error}", None

        # 2. Instantiate DynamicSkill
        skill = DynamicSkill(spec)

        # 3. Dry-run execution test
        if dry_run_input:
            test_res = skill.execute(dry_run_input)
            if not test_res.success:
                return False, f"Dry-run test failed: {test_res.error}", None

        # 4. Register skill
        self.registry.register_skill(skill)

        # 5. Pico's pencil-note celebration
        celebration = f"✏️ *Pico writes in his notebook*: New skill '{spec.name}' learned and ready to use! ✨"

        return True, celebration, skill
