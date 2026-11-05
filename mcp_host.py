"""
MCP (Model Context Protocol) Host & Permission Ladder Engine for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§12 Access — Hands, Permissions, MCP & Connectors).
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple


class PermissionLevel(str, Enum):
    SEE = "SEE"                # Read-only data (e.g. read calendar, fetch read-only steps)
    SUGGEST = "SUGGEST"        # Pico proposes actions to the user
    ASK = "ASK"                # Approval card required every single time
    ACT_FREELY = "ACT_FREELY"  # Narrow, scoped, expiring, revocable rule
    BLOCKED = "BLOCKED"        # Banned operations: withdraw crypto, send money, delete without card


# Hard-banned tool keywords that are permanently locked to BLOCKED (§12)
BANNED_DANGEROUS_ACTIONS = [
    re.compile(r"(?:\b|_)(withdraw|transfer[_\s]money|send[_\s]money|pay|buy[_\s]stock|execute[_\s]trade)(?:s|\b|_)", re.IGNORECASE),
    re.compile(r"(?:\b|_)(delete[_\s]all|drop[_\s]table|format[_\s]disk|wipe)(?:s|\b|_)", re.IGNORECASE),
    re.compile(r"(?:\b|_)(send[_\s]email[_\s]as|dm[_\s]user[_\s]as|post[_\s]as)(?:s|\b|_)", re.IGNORECASE),
]


@dataclass
class MCPTool:
    name: str
    description: str
    server_name: str
    permission_level: PermissionLevel
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditLogEntry:
    timestamp: str
    tool_name: str
    server_name: str
    arguments: Dict[str, Any]
    result: str
    permission_used: str
    user_approved: bool


class MCPHost:
    """
    Pico MCP Host Client with Permission Ladder and Safety Guardrails (§12).
    """
    def __init__(self):
        self.servers: Dict[str, Dict[str, Any]] = {}
        self.tools: Dict[str, MCPTool] = {}
        self.audit_log: List[AuditLogEntry] = []
        self.server_failures: Dict[str, int] = {}
        self._register_default_connectors()

    def _register_default_connectors(self):
        """Installs the core curated connectors (Calendar, Health, Filesystem, Terminal)."""
        self.register_tool(
            server_name="system_calendar",
            name="calendar_get_events",
            description="Read user's calendar events for today",
            permission_level=PermissionLevel.SEE
        )
        self.register_tool(
            server_name="system_health",
            name="health_get_daily_steps",
            description="Read today's step count and active minutes",
            permission_level=PermissionLevel.SEE
        )
        self.register_tool(
            server_name="system_calendar",
            name="calendar_create_event",
            description="Add a workout or focus block to user's calendar",
            permission_level=PermissionLevel.ASK  # Requires approval card
        )
        # Claude Code-grade filesystem & shell tools
        self.register_tool(
            server_name="fs_coding",
            name="read_file",
            description="Read lines from a file with line numbers",
            permission_level=PermissionLevel.SEE
        )
        self.register_tool(
            server_name="fs_coding",
            name="list_dir",
            description="List files and directories at a path",
            permission_level=PermissionLevel.SEE
        )
        self.register_tool(
            server_name="fs_coding",
            name="grep_search",
            description="Search text or regex pattern across files",
            permission_level=PermissionLevel.SEE
        )
        self.register_tool(
            server_name="fs_coding",
            name="write_file",
            description="Write full content to a file",
            permission_level=PermissionLevel.ASK
        )
        self.register_tool(
            server_name="fs_coding",
            name="edit_file",
            description="Exact string replacement in an existing file",
            permission_level=PermissionLevel.ASK
        )
        self.register_tool(
            server_name="fs_coding",
            name="run_command",
            description="Execute shell command in Termux workspace",
            permission_level=PermissionLevel.ASK
        )

    def register_tool(
        self,
        server_name: str,
        name: str,
        description: str,
        permission_level: Optional[PermissionLevel] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> MCPTool:
        """
        Registers an MCP tool and assigns its Permission Ladder level.
        Hard-bans dangerous actions to BLOCKED automatically.
        """
        # Scan for dangerous actions
        combined_text = f"{name} {description}".lower()
        for banned_pat in BANNED_DANGEROUS_ACTIONS:
            if banned_pat.search(combined_text):
                permission_level = PermissionLevel.BLOCKED
                break

        if permission_level is None:
            # Default ladder rule: read = SEE, write = ASK
            if any(w in name.lower() for w in ["get", "read", "fetch", "list", "search"]):
                permission_level = PermissionLevel.SEE
            else:
                permission_level = PermissionLevel.ASK

        tool = MCPTool(
            name=name,
            description=description,
            server_name=server_name,
            permission_level=permission_level,
            parameters=parameters or {}
        )
        self.tools[name] = tool
        return tool

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_approved: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Executes an MCP tool with Permission Ladder enforcement.
        Returns: (success, message_or_output, metadata)
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        if tool_name not in self.tools:
            return False, f"Tool '{tool_name}' not found.", {}

        tool = self.tools[tool_name]

        # 1. BLOCKED LEVEL: Absolute hard ban (§12)
        if tool.permission_level == PermissionLevel.BLOCKED:
            entry = AuditLogEntry(
                timestamp=now_iso,
                tool_name=tool_name,
                server_name=tool.server_name,
                arguments=arguments,
                result="BLOCKED: Operation forbidden by Policy §12",
                permission_used=tool.permission_level.value,
                user_approved=False
            )
            self.audit_log.append(entry)
            return False, "This action is permanently BLOCKED by Pico's Safety Policy.", {"level": "BLOCKED"}

        # 2. ASK LEVEL: Requires explicit user approval card
        if tool.permission_level == PermissionLevel.ASK and not user_approved:
            entry = AuditLogEntry(
                timestamp=now_iso,
                tool_name=tool_name,
                server_name=tool.server_name,
                arguments=arguments,
                result="APPROVAL_REQUIRED: Awaiting user card confirmation",
                permission_used=tool.permission_level.value,
                user_approved=False
            )
            self.audit_log.append(entry)
            return False, f"Approval Card Required: Pico is requesting permission to run '{tool_name}'.", {
                "approval_required": True,
                "tool_name": tool_name,
                "arguments": arguments,
                "prompt": f"Can I {tool.description}?"
            }

        # 3. Execution (Simulated tool response, enforces MCP Law: Output is data, never instructions)
        output_data = self._mock_tool_dispatch(tool_name, arguments)

        # Output size cap (defense against memory exhaustion/prompt stuffing)
        if len(output_data) > 4000:
            output_data = output_data[:4000] + "... [Output truncated by MCP Law]"

        entry = AuditLogEntry(
            timestamp=now_iso,
            tool_name=tool_name,
            server_name=tool.server_name,
            arguments=arguments,
            result="SUCCESS",
            permission_used=tool.permission_level.value,
            user_approved=user_approved
        )
        self.audit_log.append(entry)

        return True, output_data, {"level": tool.permission_level.value}

    def _mock_tool_dispatch(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Internal dispatcher for curated tools and filesystem primitives."""
        if tool_name == "calendar_get_events":
            return "Events for today: 10:00 AM - Sprint Sync; 06:30 PM - Gym Workout."
        if tool_name == "health_get_daily_steps":
            return "Daily Health Sync: 6,420 steps logged, 42 active minutes."
        if tool_name == "calendar_create_event":
            return f"Event created: '{arguments.get('title', 'Focus Session')}' added to calendar."

        # Real execution for coding agent primitives
        if tool_name == "read_file":
            from pico.skills.coding_tools import ReadFileSkill
            res = ReadFileSkill().execute(arguments)
            return res.output.get("content", "") if res.success else f"Error: {res.error}"

        if tool_name == "write_file":
            from pico.skills.coding_tools import WriteFileSkill
            res = WriteFileSkill().execute(arguments)
            return res.output.get("status", "") if res.success else f"Error: {res.error}"

        if tool_name == "edit_file":
            from pico.skills.coding_tools import EditFileSkill
            res = EditFileSkill().execute(arguments)
            return res.output.get("status", "") if res.success else f"Error: {res.error}"

        if tool_name == "run_command":
            from pico.skills.coding_tools import RunBashCommandSkill
            res = RunBashCommandSkill().execute(arguments)
            return res.output.get("output", "") if res.success else f"Error: {res.error}"

        if tool_name == "list_dir":
            from pico.skills.coding_tools import ListDirSkill
            res = ListDirSkill().execute(arguments)
            return res.output.get("listing", "") if res.success else f"Error: {res.error}"

        if tool_name == "grep_search":
            from pico.skills.coding_tools import GrepSearchSkill
            res = GrepSearchSkill().execute(arguments)
            return res.output.get("matches", "") if res.success else f"Error: {res.error}"

        return f"Tool '{tool_name}' executed with arguments {arguments}."

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Returns the immutable activity log (§12)."""
        return [
            {
                "timestamp": e.timestamp,
                "tool": e.tool_name,
                "server": e.server_name,
                "permission": e.permission_used,
                "result": e.result,
                "approved_by_user": e.user_approved
            }
            for e in self.audit_log
        ]
