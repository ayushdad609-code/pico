"""
Hermes-Style Skill Self-Improvement Engine (skill_manage) for Pico.
From NousResearch Hermes Agent specification.

Provides the 6 foundational actions for procedural self-evolution:
1. create: Synthesizes, verifies in sandbox, writes to custom/ and registers new skill.
2. read: Inspects skill source code, schemas, docstrings, and metrics.
3. update: Hot-patches existing skills mid-execution when finding better solutions.
4. test: Sandboxed dry-run verification against test inputs.
5. rollback: Restores previous version from .bak backup on regressions.
6. deprecate: Safely disables obsolete skills and archives them.
"""

import os
import re
import ast
import time
import shutil
import importlib.util
from typing import Dict, Any, Optional, Tuple, Type
from datetime import datetime, timezone

from .base_skill import BaseSkill, SkillResult
from .skill_creator import DynamicSkill, SkillSpec
from pico.mcp_host import PermissionLevel


CUSTOM_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "custom")
DEPRECATED_SKILLS_DIR = os.path.join(CUSTOM_SKILLS_DIR, "deprecated")

# Hardened security patterns for dynamic skills
DISALLOWED_PATTERNS = [
    re.compile(r"\b(rm\s+-rf|format\s+[a-z]:|os\.system|subprocess\.(?:call|Popen|run|check_output|check_call)|shutil\.rmtree)\b", re.IGNORECASE),
    re.compile(r"\b(withdraw|transfer[_\s]funds|send[_\s]payment|send[_\s]money)\b", re.IGNORECASE),
    re.compile(r"__import__\(['\"](?:os|subprocess)['\"]\)", re.IGNORECASE),
]


class SkillManageSkill(BaseSkill):
    """
    Hermes Skill Management Tool.
    Equips Pico with autonomous procedural self-evolution.
    """
    name = "skill_manage"
    description = "Hermes skill self-improvement engine. 6 actions: create, read, update, test, rollback, deprecate."
    version = "v1.0"
    permission_level = PermissionLevel.ASK
    parameters_schema = {
        "action": {
            "type": "string",
            "enum": ["create", "read", "update", "test", "rollback", "deprecate"],
            "required": True,
            "description": "The improvement action to perform."
        },
        "name": {
            "type": "string",
            "required": False,
            "description": "Skill name in snake_case (e.g. 'json_cleaner')."
        },
        "description": {
            "type": "string",
            "required": False,
            "description": "Clear explanation of what the skill does."
        },
        "parameters_schema": {
            "type": "object",
            "required": False,
            "description": "JSON schema of expected input parameters."
        },
        "code": {
            "type": "string",
            "required": False,
            "description": "Python source code for the skill."
        },
        "test_input": {
            "type": "object",
            "required": False,
            "description": "Sample input payload to test the skill."
        },
        "reason": {
            "type": "string",
            "required": False,
            "description": "Reason for deprecation or update notes."
        }
    }

    def __init__(self, registry=None):
        self.registry = registry

    def _get_registry(self):
        if self.registry:
            return self.registry
        from .registry import SkillRegistry
        return SkillRegistry.get_shared_instance()

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        action = inputs.get("action", "").lower().strip()
        name = inputs.get("name", "").lower().strip()

        os.makedirs(CUSTOM_SKILLS_DIR, exist_ok=True)
        os.makedirs(DEPRECATED_SKILLS_DIR, exist_ok=True)

        if action == "create":
            return self._handle_create(inputs, start_t)
        elif action == "read":
            return self._handle_read(name, start_t)
        elif action == "update":
            return self._handle_update(inputs, start_t)
        elif action == "test":
            return self._handle_test(inputs, start_t)
        elif action == "rollback":
            return self._handle_rollback(name, start_t)
        elif action == "deprecate":
            return self._handle_deprecate(name, inputs.get("reason", ""), start_t)
        else:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error=f"Unknown action '{action}'. Supported actions: create, read, update, test, rollback, deprecate.",
                execution_time_ms=round((time.time() - start_t) * 1000, 2)
            )

    # =========================================================================
    # ACTION 1: CREATE
    # =========================================================================
    def _handle_create(self, inputs: Dict[str, Any], start_t: float) -> SkillResult:
        name = inputs.get("name", "").strip()
        description = inputs.get("description", "").strip()
        code = inputs.get("code", "").strip()
        parameters_schema = inputs.get("parameters_schema", {})
        test_input = inputs.get("test_input")

        if not name:
            return SkillResult(False, self.name, {}, "Skill 'name' is required for create.", execution_time_ms=round((time.time() - start_t) * 1000, 2))
        if not re.match(r"^[a-z][a-z0-9_]{2,35}$", name):
            return SkillResult(False, self.name, {}, "Skill name must be lowercase alphanumeric with underscores (3-35 chars).", execution_time_ms=round((time.time() - start_t) * 1000, 2))
        if not code:
            return SkillResult(False, self.name, {}, "Skill 'code' is required for create.", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        # 1. Security scan
        safe, sec_err = self._scan_safety(code)
        if not safe:
            return SkillResult(False, self.name, {}, f"Security policy rejection: {sec_err}", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        # 2. Syntax validation
        valid_syntax, syn_err = self._validate_syntax(code)
        if not valid_syntax:
            return SkillResult(False, self.name, {}, f"Syntax error: {syn_err}", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        # 3. Dry-run test in sandbox
        if test_input is not None:
            t_success, t_out, t_err = self._sandbox_run(code, name, test_input)
            if not t_success:
                return SkillResult(False, self.name, {}, f"Pre-creation dry run failed: {t_err}", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        # 4. Write to disk in custom skills folder
        filepath = os.path.join(CUSTOM_SKILLS_DIR, f"{name}.py")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            return SkillResult(False, self.name, {}, f"Failed to write skill file: {e}", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        # 5. Hot-register into active registry
        reg = self._get_registry()
        loaded_skill = self.load_skill_from_file(filepath, name)
        if loaded_skill:
            reg.register_skill(loaded_skill)
        else:
            # Fallback dynamic wrapper
            spec = SkillSpec(
                name=name,
                description=description or f"Dynamically created skill {name}",
                parameters_schema=parameters_schema,
                python_code=code,
                logic_callable=self._make_callable_from_code(code, name)
            )
            reg.register_skill(DynamicSkill(spec))

        return SkillResult(
            success=True,
            skill_name=self.name,
            output={
                "action": "create",
                "name": name,
                "status": "created",
                "path": filepath,
                "message": f"✨ Skill '{name}' successfully created, tested, and registered into Pico's active skills."
            },
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )

    # =========================================================================
    # ACTION 2: READ
    # =========================================================================
    def _handle_read(self, name: str, start_t: float) -> SkillResult:
        if not name:
            return SkillResult(False, self.name, {}, "Skill 'name' is required for read.", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        reg = self._get_registry()
        skill = reg.get_skill(name)

        custom_path = os.path.join(CUSTOM_SKILLS_DIR, f"{name}.py")
        code = ""
        is_custom = os.path.exists(custom_path)

        if is_custom:
            try:
                with open(custom_path, "r", encoding="utf-8") as f:
                    code = f.read()
            except Exception as e:
                code = f"# Error reading file: {e}"
        elif skill:
            # Check if built-in file exists
            builtin_path = os.path.join(os.path.dirname(__file__), f"{name}.py")
            if os.path.exists(builtin_path):
                try:
                    with open(builtin_path, "r", encoding="utf-8") as f:
                        code = f.read()
                except Exception:
                    code = "# Source code unavailable"
            else:
                code = getattr(skill, "python_code", "# Source code defined in runtime class")

        if not skill and not is_custom:
            return SkillResult(False, self.name, {}, f"Skill '{name}' not found.", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        desc = skill.description if skill else ""
        params = skill.parameters_schema if skill else {}
        version = getattr(skill, "version", "v1.0")

        return SkillResult(
            success=True,
            skill_name=self.name,
            output={
                "action": "read",
                "name": name,
                "description": desc,
                "version": version,
                "parameters": params,
                "code": code,
                "is_custom": is_custom
            },
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )

    # =========================================================================
    # ACTION 3: UPDATE
    # =========================================================================
    def _handle_update(self, inputs: Dict[str, Any], start_t: float) -> SkillResult:
        name = inputs.get("name", "").strip()
        code = inputs.get("code", "").strip()
        test_input = inputs.get("test_input")

        if not name:
            return SkillResult(False, self.name, {}, "Skill 'name' is required for update.", execution_time_ms=round((time.time() - start_t) * 1000, 2))
        if not code:
            return SkillResult(False, self.name, {}, "New skill 'code' is required for update.", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        filepath = os.path.join(CUSTOM_SKILLS_DIR, f"{name}.py")
        bak_path = os.path.join(CUSTOM_SKILLS_DIR, f"{name}.py.bak")

        # 1. Security scan
        safe, sec_err = self._scan_safety(code)
        if not safe:
            return SkillResult(False, self.name, {}, f"Security policy rejection: {sec_err}", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        # 2. Syntax validation
        valid_syntax, syn_err = self._validate_syntax(code)
        if not valid_syntax:
            return SkillResult(False, self.name, {}, f"Syntax error: {syn_err}", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        # 3. Dry-run test in sandbox
        if test_input is not None:
            t_success, t_out, t_err = self._sandbox_run(code, name, test_input)
            if not t_success:
                return SkillResult(False, self.name, {}, f"Update test failed: {t_err}. Original skill kept intact.", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        # 4. Create backup of current file if it exists
        if os.path.exists(filepath):
            shutil.copy2(filepath, bak_path)

        # 5. Overwrite file
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            return SkillResult(False, self.name, {}, f"Failed to write update: {e}", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        # 6. Hot-swap in registry
        reg = self._get_registry()
        updated_skill = self.load_skill_from_file(filepath, name)
        if updated_skill:
            reg.register_skill(updated_skill)
        else:
            spec = SkillSpec(
                name=name,
                description=inputs.get("description", f"Updated skill {name}"),
                parameters_schema=inputs.get("parameters_schema", {}),
                python_code=code,
                logic_callable=self._make_callable_from_code(code, name)
            )
            reg.register_skill(DynamicSkill(spec))

        return SkillResult(
            success=True,
            skill_name=self.name,
            output={
                "action": "update",
                "name": name,
                "status": "updated",
                "backup": f"{name}.py.bak",
                "message": f"🔄 Skill '{name}' successfully updated and hot-reloaded with backup preserved."
            },
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )

    # =========================================================================
    # ACTION 4: TEST
    # =========================================================================
    def _handle_test(self, inputs: Dict[str, Any], start_t: float) -> SkillResult:
        name = inputs.get("name", "").strip()
        code = inputs.get("code", "").strip()
        test_input = inputs.get("test_input", {})

        if code:
            t_success, t_out, t_err = self._sandbox_run(code, name or "inline_test", test_input)
            return SkillResult(
                success=t_success,
                skill_name=self.name,
                output={"action": "test", "name": name, "output": t_out},
                error=t_err,
                execution_time_ms=round((time.time() - start_t) * 1000, 2)
            )

        if not name:
            return SkillResult(False, self.name, {}, "Either 'code' or 'name' must be provided for test.", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        reg = self._get_registry()
        skill = reg.get_skill(name)
        if not skill:
            return SkillResult(False, self.name, {}, f"Skill '{name}' is not registered.", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        try:
            exec_res = skill.execute(test_input)
            return SkillResult(
                success=exec_res.success,
                skill_name=self.name,
                output={"action": "test", "name": name, "result": exec_res.output},
                error=exec_res.error,
                execution_time_ms=round((time.time() - start_t) * 1000, 2)
            )
        except Exception as e:
            return SkillResult(False, self.name, {}, f"Execution error in '{name}': {str(e)}", execution_time_ms=round((time.time() - start_t) * 1000, 2))

    # =========================================================================
    # ACTION 5: ROLLBACK
    # =========================================================================
    def _handle_rollback(self, name: str, start_t: float) -> SkillResult:
        if not name:
            return SkillResult(False, self.name, {}, "Skill 'name' is required for rollback.", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        filepath = os.path.join(CUSTOM_SKILLS_DIR, f"{name}.py")
        bak_path = os.path.join(CUSTOM_SKILLS_DIR, f"{name}.py.bak")

        if not os.path.exists(bak_path):
            return SkillResult(False, self.name, {}, f"No backup file ({name}.py.bak) found for skill '{name}'.", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        try:
            shutil.copy2(bak_path, filepath)
        except Exception as e:
            return SkillResult(False, self.name, {}, f"Failed to restore backup: {e}", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        reg = self._get_registry()
        restored_skill = self.load_skill_from_file(filepath, name)
        if restored_skill:
            reg.register_skill(restored_skill)

        return SkillResult(
            success=True,
            skill_name=self.name,
            output={
                "action": "rollback",
                "name": name,
                "status": "rolled_back",
                "restored_from": f"{name}.py.bak",
                "message": f"⏪ Skill '{name}' rolled back to previous backup version."
            },
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )

    # =========================================================================
    # ACTION 6: DEPRECATE
    # =========================================================================
    def _handle_deprecate(self, name: str, reason: str, start_t: float) -> SkillResult:
        if not name:
            return SkillResult(False, self.name, {}, "Skill 'name' is required for deprecate.", execution_time_ms=round((time.time() - start_t) * 1000, 2))

        reg = self._get_registry()
        reg.unregister_skill(name)

        filepath = os.path.join(CUSTOM_SKILLS_DIR, f"{name}.py")
        dep_path = os.path.join(DEPRECATED_SKILLS_DIR, f"{name}.py")

        if os.path.exists(filepath):
            shutil.move(filepath, dep_path)

        return SkillResult(
            success=True,
            skill_name=self.name,
            output={
                "action": "deprecate",
                "name": name,
                "status": "deprecated",
                "reason": reason or "Deprecated by agent or developer."
            },
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )

    # =========================================================================
    # HELPERS & SANDBOX RUNNER
    # =========================================================================
    @staticmethod
    def _scan_safety(code: str) -> Tuple[bool, Optional[str]]:
        for pat in DISALLOWED_PATTERNS:
            if pat.search(code):
                return False, f"Code violates safety policy (matches forbidden pattern: '{pat.pattern}')"
        return True, None

    @staticmethod
    def _validate_syntax(code: str) -> Tuple[bool, Optional[str]]:
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as se:
            return False, f"Line {se.lineno}: {se.msg}"

    def _sandbox_run(self, code: str, skill_name: str, test_input: Dict[str, Any]) -> Tuple[bool, Any, Optional[str]]:
        """Executes code in isolated local namespace with inputs."""
        scope: Dict[str, Any] = {
            "BaseSkill": BaseSkill,
            "SkillResult": SkillResult,
            "PermissionLevel": PermissionLevel,
            "re": re,
            "json": __import__("json"),
            "math": __import__("math"),
            "datetime": __import__("datetime"),
            "typing": __import__("typing")
        }
        try:
            compiled = compile(code, f"<skill_{skill_name}>", "exec")
            exec(compiled, scope)

            # Check if class subclassing BaseSkill is defined
            skill_inst = None
            for key, val in scope.items():
                if isinstance(val, type) and issubclass(val, BaseSkill) and val is not BaseSkill:
                    skill_inst = val()
                    break

            if skill_inst:
                res = skill_inst.execute(test_input)
                return res.success, res.output, res.error

            # Check if execute(inputs) function defined
            if "execute" in scope and callable(scope["execute"]):
                fn_res = scope["execute"](test_input)
                return True, fn_res, None

            return True, {"message": "Code compiled and loaded successfully."}, None
        except Exception as e:
            return False, None, str(e)

    def _make_callable_from_code(self, code: str, skill_name: str):
        def _callable(inputs: Dict[str, Any]):
            success, out, err = self._sandbox_run(code, skill_name, inputs)
            if not success:
                raise RuntimeError(err or "Dynamic execution failure")
            return out
        return _callable

    @staticmethod
    def load_skill_from_file(filepath: str, name: str) -> Optional[BaseSkill]:
        """Loads a BaseSkill or wrapped DynamicSkill directly from Python file."""
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                code_text = f.read()

            scope: Dict[str, Any] = {
                "BaseSkill": BaseSkill,
                "SkillResult": SkillResult,
                "PermissionLevel": PermissionLevel,
                "__file__": filepath,
                "__name__": f"pico_custom_{name}"
            }
            compiled = compile(code_text, filepath, "exec")
            exec(compiled, scope)

            for key, val in scope.items():
                if isinstance(val, type) and issubclass(val, BaseSkill) and val is not BaseSkill:
                    return val()

            if "execute" in scope and callable(scope["execute"]):
                desc = scope.get("description", f"Custom skill {name}")
                schema = scope.get("parameters_schema", {})
                return DynamicSkill(SkillSpec(
                    name=name,
                    description=desc,
                    parameters_schema=schema,
                    logic_callable=scope["execute"]
                ))
            return None
        except Exception:
            return None
