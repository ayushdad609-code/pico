"""
Base Skill Specification for Pico.
Standardizes how built-in and dynamically created skills execute.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pico.mcp_host import PermissionLevel


@dataclass
class SkillResult:
    success: bool
    skill_name: str
    output: Any
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BaseSkill(ABC):
    """Abstract Base Class for all built-in and dynamically created skills."""
    name: str = "base_skill"
    description: str = "Base skill description"
    version: str = "v1.0"
    permission_level: PermissionLevel = PermissionLevel.SEE
    parameters_schema: Dict[str, Any] = {}

    @abstractmethod
    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        """Executes the skill logic."""
        pass

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validates that required parameters are present."""
        for param, rules in self.parameters_schema.items():
            if rules.get("required", False) and param not in inputs:
                return False
        return True
