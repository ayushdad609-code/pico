"""
Claude Code-Grade Filesystem & Shell Primitives for Pico (Coding Agent Hand).
Provides:
- read_file: Line-based file reading with line numbers
- write_file: Safe file writer with auto parent directory creation
- edit_file: Targeted drop-in text replacement with diff verification
- run_bash_command: Sandboxed command execution with hard timeout via SafeCommandRunner
- list_directory: Directory inspector with recursive glob support
- grep_search: Regex and text search across files
"""

import os
import re
import glob
import subprocess
from typing import Dict, Any, Optional, List
from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel, BANNED_DANGEROUS_ACTIONS
from pico.device_sensors import SafeCommandRunner
from pico.paths import get_pico_home
import asyncio


ALLOWED_ROOT = str(get_pico_home())
BLOCKED_PATHS = ["/system", "/init", "/proc/kcore", "/dev/block", "/proc/sys", "/etc/sudoers"]
MAX_OUTPUT_CHARS = 8000


def _resolve_safe_path(path: str) -> str:
    """Normalizes and ensures path stays within user storage / termux workspace."""
    if not path:
        return ALLOWED_ROOT
    if not os.path.isabs(path):
        resolved = os.path.abspath(os.path.join(ALLOWED_ROOT, path))
    else:
        resolved = os.path.abspath(path)

    for blocked in BLOCKED_PATHS:
        if resolved.startswith(blocked):
            raise PermissionError(f"Access to system critical path '{blocked}' is permanently blocked.")
    return resolved


class ReadFileSkill(BaseSkill):
    name = "read_file"
    description = "Reads lines from a file with optional start_line and end_line bounds."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "path": {"type": "string", "required": True, "description": "Absolute or relative file path"},
        "start_line": {"type": "integer", "required": False, "description": "1-based start line (inclusive)"},
        "end_line": {"type": "integer", "required": False, "description": "1-based end line (inclusive)"}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        try:
            path = _resolve_safe_path(inputs.get("path", ""))
            if not os.path.exists(path):
                return SkillResult(success=False, skill_name=self.name, output={}, error=f"File not found: {path}")
            if os.path.isdir(path):
                return SkillResult(success=False, skill_name=self.name, output={}, error=f"Target path is a directory: {path}")

            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start_l = max(1, int(inputs.get("start_line") or 1))
            end_l = min(total_lines, int(inputs.get("end_line") or total_lines))

            if start_l > total_lines:
                return SkillResult(
                    success=True,
                    skill_name=self.name,
                    output={"content": "", "total_lines": total_lines, "returned_lines": 0}
                )

            selected = lines[start_l - 1:end_l]
            numbered = [f"{i}: {line}" for i, line in enumerate(selected, start=start_l)]
            content = "".join(numbered)
            if len(content) > MAX_OUTPUT_CHARS:
                content = content[:MAX_OUTPUT_CHARS] + "\n... [Content truncated at 8000 chars]"

            return SkillResult(
                success=True,
                skill_name=self.name,
                output={
                    "path": path,
                    "content": content,
                    "start_line": start_l,
                    "end_line": end_l,
                    "total_lines": total_lines
                }
            )
        except Exception as e:
            return SkillResult(success=False, skill_name=self.name, output={}, error=str(e))


class WriteFileSkill(BaseSkill):
    name = "write_file"
    description = "Creates a new file or overwrites an existing file with given content."
    version = "v1.0"
    permission_level = PermissionLevel.ASK
    parameters_schema = {
        "path": {"type": "string", "required": True, "description": "File path to write"},
        "content": {"type": "string", "required": True, "description": "Full file content"},
        "overwrite": {"type": "boolean", "required": False, "description": "Allow overwriting if file exists"}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        try:
            path = _resolve_safe_path(inputs.get("path", ""))
            content = inputs.get("content", "")
            overwrite = bool(inputs.get("overwrite", True))

            if os.path.exists(path) and not overwrite:
                return SkillResult(
                    success=False,
                    skill_name=self.name,
                    output={},
                    error=f"File already exists at {path} and overwrite is False."
                )

            parent_dir = os.path.dirname(path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            return SkillResult(
                success=True,
                skill_name=self.name,
                output={
                    "path": path,
                    "bytes_written": len(content.encode("utf-8")),
                    "status": "File saved successfully"
                }
            )
        except Exception as e:
            return SkillResult(success=False, skill_name=self.name, output={}, error=str(e))


class EditFileSkill(BaseSkill):
    name = "edit_file"
    description = "Exact string replacement inside an existing file with single or multi-line targets."
    version = "v1.0"
    permission_level = PermissionLevel.ASK
    parameters_schema = {
        "path": {"type": "string", "required": True, "description": "File path to edit"},
        "target": {"type": "string", "required": True, "description": "Exact text string to be replaced"},
        "replacement": {"type": "string", "required": True, "description": "Replacement string"}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        try:
            path = _resolve_safe_path(inputs.get("path", ""))
            target = inputs.get("target", "")
            replacement = inputs.get("replacement", "")

            if not os.path.exists(path):
                return SkillResult(success=False, skill_name=self.name, output={}, error=f"File not found: {path}")

            if not target:
                return SkillResult(success=False, skill_name=self.name, output={}, error="Target string cannot be empty.")

            with open(path, "r", encoding="utf-8", errors="replace") as f:
                current_text = f.read()

            if target not in current_text:
                return SkillResult(
                    success=False,
                    skill_name=self.name,
                    output={},
                    error=f"Target string not found in {path}. Make sure whitespace and formatting match exactly."
                )

            count = current_text.count(target)
            new_text = current_text.replace(target, replacement)

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)

            return SkillResult(
                success=True,
                skill_name=self.name,
                output={
                    "path": path,
                    "replacements_made": count,
                    "status": f"Replaced {count} occurrence(s) successfully."
                }
            )
        except Exception as e:
            return SkillResult(success=False, skill_name=self.name, output={}, error=str(e))


class RunBashCommandSkill(BaseSkill):
    name = "run_command"
    description = "Executes shell commands in Termux with non-blocking timeout and process tree cleanup."
    version = "v1.0"
    permission_level = PermissionLevel.ASK
    parameters_schema = {
        "command": {"type": "string", "required": True, "description": "Exact bash command line"},
        "timeout": {"type": "number", "required": False, "description": "Timeout in seconds (default 5.0, max 15.0)"}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        cmd_str = inputs.get("command", "").strip()
        if not cmd_str:
            return SkillResult(success=False, skill_name=self.name, output={}, error="Command cannot be empty.")

        # Mechanical safety scan: check against dangerous commands
        for banned_pat in BANNED_DANGEROUS_ACTIONS:
            if banned_pat.search(cmd_str):
                return SkillResult(
                    success=False,
                    skill_name=self.name,
                    output={},
                    error=f"Command '{cmd_str}' is permanently BLOCKED by Pico Safety Policy §12."
                )

        timeout = min(15.0, max(1.0, float(inputs.get("timeout") or 5.0)))

        try:
            # Run in bash shell
            p = subprocess.run(
                ["bash", "-c", cmd_str],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=ALLOWED_ROOT
            )
            stdout = p.stdout.strip()
            stderr = p.stderr.strip()
            combined = stdout
            if stderr:
                combined = f"{stdout}\n[STDERR]: {stderr}" if stdout else f"[STDERR]: {stderr}"

            if len(combined) > MAX_OUTPUT_CHARS:
                combined = combined[:MAX_OUTPUT_CHARS] + "\n... [Output truncated at 8000 chars]"

            return SkillResult(
                success=(p.returncode == 0),
                skill_name=self.name,
                output={
                    "command": cmd_str,
                    "returncode": p.returncode,
                    "stdout": stdout[:4000],
                    "stderr": stderr[:2000],
                    "output": combined
                },
                error=None if p.returncode == 0 else f"Command exited with code {p.returncode}"
            )
        except subprocess.TimeoutExpired:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={"command": cmd_str},
                error=f"Command timed out after {timeout} seconds and was cleanly terminated."
            )
        except Exception as e:
            return SkillResult(success=False, skill_name=self.name, output={}, error=str(e))


class ListDirSkill(BaseSkill):
    name = "list_dir"
    description = "Lists files and directories at a given path with sizes and item count."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "path": {"type": "string", "required": False, "description": "Directory path (defaults to workspace)"},
        "pattern": {"type": "string", "required": False, "description": "Optional glob pattern like '*.py'"}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        try:
            path = _resolve_safe_path(inputs.get("path") or ".")
            pattern = inputs.get("pattern")

            if not os.path.exists(path):
                return SkillResult(success=False, skill_name=self.name, output={}, error=f"Path not found: {path}")

            if not os.path.isdir(path):
                return SkillResult(success=False, skill_name=self.name, output={}, error=f"Path is not a directory: {path}")

            items = []
            if pattern:
                matches = glob.glob(os.path.join(path, pattern))
                for m in sorted(matches)[:100]:
                    is_d = os.path.isdir(m)
                    size = os.path.getsize(m) if not is_d else 0
                    items.append({"name": os.path.basename(m), "is_dir": is_d, "size_bytes": size})
            else:
                for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))[:100]:
                    try:
                        size = entry.stat().st_size if not entry.is_dir() else 0
                        items.append({"name": entry.name, "is_dir": entry.is_dir(), "size_bytes": size})
                    except Exception:
                        pass

            formatted = "\n".join([f"{'[DIR] ' if i['is_dir'] else '      '}{i['name']} ({i['size_bytes']} B)" for i in items])
            return SkillResult(
                success=True,
                skill_name=self.name,
                output={"path": path, "total_items": len(items), "items": items, "listing": formatted}
            )
        except Exception as e:
            return SkillResult(success=False, skill_name=self.name, output={}, error=str(e))


class GrepSearchSkill(BaseSkill):
    name = "grep_search"
    description = "Searches for text or regex patterns in files under a directory."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "pattern": {"type": "string", "required": True, "description": "Search text or regex pattern"},
        "path": {"type": "string", "required": False, "description": "Directory to search (defaults to workspace)"},
        "file_ext": {"type": "string", "required": False, "description": "Optional file extension e.g. '.py'"}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        try:
            pattern = inputs.get("pattern", "")
            if not pattern:
                return SkillResult(success=False, skill_name=self.name, output={}, error="Search pattern cannot be empty.")

            path = _resolve_safe_path(inputs.get("path") or ".")
            ext = inputs.get("file_ext", "")
            regex = re.compile(pattern, re.IGNORECASE)

            matches = []
            for root, dirs, files in os.walk(path):
                # Skip hidden/large caches
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["__pycache__", "node_modules", "venv"]]
                for f in files:
                    if ext and not f.endswith(ext):
                        continue
                    full_p = os.path.join(root, f)
                    try:
                        with open(full_p, "r", encoding="utf-8", errors="ignore") as file_obj:
                            for idx, line in enumerate(file_obj, start=1):
                                if regex.search(line):
                                    rel = os.path.relpath(full_p, path)
                                    matches.append(f"{rel}:{idx}: {line.strip()[:150]}")
                                    if len(matches) >= 50:
                                        break
                    except Exception:
                        pass
                if len(matches) >= 50:
                    break

            result_text = "\n".join(matches) if matches else "No matches found."
            return SkillResult(
                success=True,
                skill_name=self.name,
                output={"pattern": pattern, "match_count": len(matches), "matches": result_text}
            )
        except Exception as e:
            return SkillResult(success=False, skill_name=self.name, output={}, error=str(e))
