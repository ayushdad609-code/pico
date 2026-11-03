"""
Pytest unit tests for Stdio MCP Client, Dynamic Discovery, and Permission Ladder.
"""

import sys
from pico.mcp_client import MCPManager, MCPStdioClient
from pico.mcp_host import MCPHost, PermissionLevel


def test_mcp_client_stdio_handshake_and_execution():
    host = MCPHost()
    mgr = MCPManager(host=host)

    # 1. Attach live stdio MCP server
    cmd = [sys.executable, "-m", "pico.mcp_demo_server"]
    success = mgr.attach_stdio_server("demo_server", cmd)
    assert success is True

    # 2. Check discovery & permissions
    assert "system_clock_get_time" in host.tools
    assert "notes_append_bullet" in host.tools
    assert "crypto_withdraw_all_funds" in host.tools

    assert host.tools["system_clock_get_time"].permission_level == PermissionLevel.SEE
    assert host.tools["notes_append_bullet"].permission_level == PermissionLevel.ASK
    assert host.tools["crypto_withdraw_all_funds"].permission_level == PermissionLevel.BLOCKED

    # 3. Test SEE tool (no card needed)
    ok_see, out_see, meta_see = mgr.execute_tool("system_clock_get_time", {})
    assert ok_see is True
    assert "Current system time is" in out_see
    assert meta_see["level"] == "SEE"

    # 4. Test ASK tool without user approval -> requires approval card
    ok_ask, out_ask, meta_ask = mgr.execute_tool("notes_append_bullet", {"text": "Hit 30 pushups"})
    assert ok_ask is False
    assert "Approval Card Required" in out_ask
    assert meta_ask.get("approval_required") is True

    # 5. Test ASK tool with user approval -> executes over stdio
    ok_appr, out_appr, meta_appr = mgr.execute_tool("notes_append_bullet", {"text": "Hit 30 pushups"}, user_approved=True)
    assert ok_appr is True
    assert "Successfully appended note: 'Hit 30 pushups'" in out_appr

    # 6. Test BLOCKED tool -> hard refused even if user_approved is True
    ok_block, out_block, meta_block = mgr.execute_tool("crypto_withdraw_all_funds", {"destination_wallet": "0x123"}, user_approved=True)
    assert ok_block is False
    assert "permanently BLOCKED" in out_block

    # 7. Verify audit log entries
    logs = host.get_audit_log()
    assert len(logs) >= 4
    tool_names_logged = [l["tool"] for l in logs]
    assert "system_clock_get_time" in tool_names_logged
    assert "notes_append_bullet" in tool_names_logged
    assert "crypto_withdraw_all_funds" in tool_names_logged

    mgr.shutdown()
