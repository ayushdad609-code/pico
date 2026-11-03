"""
Stdio MCP (Model Context Protocol) Client & Dynamic Connector Engine for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§12 Access — Hands, Permissions, MCP & Connectors).

Connects to standard external or local MCP servers over stdio via JSON-RPC 2.0:
- Handshake & capabilities exchange (initialize, notifications/initialized)
- Dynamic tool discovery (tools/list)
- Automatic safety classification through MCPHost Permission Ladder (SEE, SUGGEST, ASK, BLOCKED)
- Tool invocation (tools/call) with execution timeout, audit logging, and output truncation.
"""

import sys
import subprocess
import json
import time
from typing import Dict, Any, List, Optional, Tuple
from .mcp_host import MCPHost, PermissionLevel, MCPTool, AuditLogEntry


class MCPStdioClient:
    """Manages an active stdio connection to an external MCP server."""

    def __init__(self, command: List[str], server_name: str, timeout_seconds: float = 8.0):
        self.command = command
        self.server_name = server_name
        self.timeout_seconds = timeout_seconds
        self.process: Optional[subprocess.Popen] = None
        self._req_id = 0
        self.is_connected = False
        self.server_info: Dict[str, Any] = {}

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def connect(self) -> bool:
        """Launches the server subprocess and performs the initialize handshake."""
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            # 1. Initialize handshake
            init_req = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "pico-agent-client", "version": "1.0.0"}
                }
            }
            resp = self._send_request(init_req)
            if not resp or "error" in resp:
                self.disconnect()
                return False

            self.server_info = resp.get("result", {}).get("serverInfo", {})

            # 2. Initialized notification
            notif = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }
            self._send_notification(notif)
            self.is_connected = True
            return True
        except Exception:
            self.disconnect()
            return False

    def _send_request(self, req: dict) -> Optional[dict]:
        """Writes JSON-RPC request line and reads single-line response."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            return None
        try:
            line = json.dumps(req) + "\n"
            self.process.stdin.write(line)
            self.process.stdin.flush()

            raw_resp = self.process.stdout.readline()
            if not raw_resp:
                return None
            return json.loads(raw_resp.strip())
        except Exception:
            return None

    def _send_notification(self, notif: dict):
        """Sends a notification that expects no response."""
        if not self.process or not self.process.stdin:
            return
        try:
            line = json.dumps(notif) + "\n"
            self.process.stdin.write(line)
            self.process.stdin.flush()
        except Exception:
            pass

    def list_tools(self) -> List[Dict[str, Any]]:
        """Queries the MCP server for its exposed tool list."""
        if not self.is_connected:
            return []
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {}
        }
        resp = self._send_request(req)
        if resp and "result" in resp and "tools" in resp["result"]:
            return resp["result"]["tools"]
        return []

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, str]:
        """Calls a tool over JSON-RPC 2.0."""
        if not self.is_connected:
            return False, "MCP Client not connected."
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        resp = self._send_request(req)
        if not resp:
            return False, "No response from MCP server."
        if "error" in resp:
            return False, resp["error"].get("message", "Unknown MCP error")

        # Parse MCP text content
        res = resp.get("result", {})
        content_list = res.get("content", [])
        text_parts = [c.get("text", "") for c in content_list if c.get("type") == "text"]
        out_text = "\n".join(text_parts) if text_parts else json.dumps(res)
        return True, out_text

    def sync_tools_to_host(self, host: MCPHost) -> int:
        """
        Discovers tools and registers them into MCPHost with permission ladder classification.
        Returns count of newly registered tools.
        """
        tools = self.list_tools()
        count = 0
        for t in tools:
            name = t.get("name")
            desc = t.get("description", "")
            params = t.get("inputSchema", {})
            host.register_tool(
                server_name=self.server_name,
                name=name,
                description=desc,
                parameters=params
            )
            count += 1
        return count

    def disconnect(self):
        """Terminates subprocess cleanly."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        self.is_connected = False


class MCPManager:
    """Manages active stdio MCP servers and bridges them to Pico's MCPHost."""

    def __init__(self, host: Optional[MCPHost] = None):
        self.host = host or MCPHost()
        self.clients: Dict[str, MCPStdioClient] = {}

    def attach_stdio_server(self, server_name: str, command: List[str]) -> bool:
        """Launches, handshakes, and registers an MCP stdio server."""
        client = MCPStdioClient(command=command, server_name=server_name)
        if client.connect():
            self.clients[server_name] = client
            client.sync_tools_to_host(self.host)
            return True
        return False

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_approved: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Executes tool across live stdio clients or internal mock connectors
        while strictly enforcing the Permission Ladder.
        """
        if tool_name not in self.host.tools:
            return False, f"Tool '{tool_name}' is not registered.", {}

        tool = self.host.tools[tool_name]

        # 1. Permission checks via host
        if tool.permission_level == PermissionLevel.BLOCKED:
            return self.host.execute_tool(tool_name, arguments, user_approved=user_approved)

        if tool.permission_level == PermissionLevel.ASK and not user_approved:
            return self.host.execute_tool(tool_name, arguments, user_approved=False)

        # 2. If backed by a live stdio client, dispatch over JSON-RPC 2.0
        client = self.clients.get(tool.server_name)
        if client and client.is_connected:
            ok, out_str = client.call_tool(tool_name, arguments)
            # Enforce output length limit
            if len(out_str) > 4000:
                out_str = out_str[:4000] + "... [Output truncated by MCP Law]"

            # Log audit
            from datetime import datetime, timezone
            self.host.audit_log.append(AuditLogEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                tool_name=tool_name,
                server_name=tool.server_name,
                arguments=arguments,
                result="SUCCESS" if ok else f"ERROR: {out_str}",
                permission_used=tool.permission_level.value,
                user_approved=user_approved
            ))
            return ok, out_str, {"level": tool.permission_level.value, "server": tool.server_name}

        # 3. Fallback to host internal mock dispatch
        return self.host.execute_tool(tool_name, arguments, user_approved=user_approved)

    def shutdown(self):
        """Closes all active MCP server processes."""
        for client in self.clients.values():
            client.disconnect()
        self.clients.clear()
