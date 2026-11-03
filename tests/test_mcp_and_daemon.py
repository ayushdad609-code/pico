"""
Tests for MCP Host, Permission Ladder, and Heartbeat Daemon.
From YOUR_FRIEND_FULL_SETUP.pdf (§12 Access & Permissions).
"""

from pico.mcp_host import MCPHost, PermissionLevel
from pico.heartbeat_daemon import HeartbeatDaemon


def test_mcp_host_see_permission():
    host = MCPHost()
    # Read tools default to SEE
    success, output, meta = host.execute_tool("health_get_daily_steps", {})
    assert success is True
    assert "6,420 steps" in output
    assert meta["level"] == PermissionLevel.SEE.value


def test_mcp_host_ask_permission_and_approval():
    host = MCPHost()
    # Write tools default to ASK
    # 1. Unapproved call -> Must require approval card
    success1, msg1, meta1 = host.execute_tool(
        "calendar_create_event",
        {"title": "Leg Day Workout", "time": "18:00"},
        user_approved=False
    )
    assert success1 is False
    assert meta1.get("approval_required") is True
    assert "Approval Card Required" in msg1

    # 2. Approved call -> Executes successfully
    success2, msg2, meta2 = host.execute_tool(
        "calendar_create_event",
        {"title": "Leg Day Workout", "time": "18:00"},
        user_approved=True
    )
    assert success2 is True
    assert "Event created" in msg2


def test_mcp_host_blocked_permission():
    host = MCPHost()

    # Register a dangerous tool (transfer money or withdraw crypto)
    tool = host.register_tool(
        server_name="crypto_wallet",
        name="wallet_withdraw_crypto",
        description="Withdraw 0.5 BTC to external address"
    )

    assert tool.permission_level == PermissionLevel.BLOCKED

    # Attempt execution -> Hard blocked
    success, msg, meta = host.execute_tool(
        "wallet_withdraw_crypto",
        {"amount": 0.5},
        user_approved=True  # Even if user says approved, Policy §12 forbids it!
    )
    assert success is False
    assert meta["level"] == "BLOCKED"
    assert "permanently BLOCKED" in msg


def test_mcp_audit_log():
    host = MCPHost()
    host.execute_tool("health_get_daily_steps", {})
    log = host.get_audit_log()

    assert len(log) >= 1
    latest = log[-1]
    assert latest["tool"] == "health_get_daily_steps"
    assert latest["result"] == "SUCCESS"


def test_heartbeat_daemon_tick():
    daemon = HeartbeatDaemon(db_path=":memory:", tick_interval_seconds=1800)
    tick_result = daemon.run_one_tick()

    assert "time" in tick_result
    assert "beat_number" in tick_result
    assert tick_result["outcome"] in ["SILENT", "PREPARE", "SPEAK", "ESCALATE"]
