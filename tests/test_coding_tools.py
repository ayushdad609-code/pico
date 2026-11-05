"""
Tests for Claude Code-grade filesystem and shell primitives in Pico.
"""

import os
import pytest
from pico.skills.coding_tools import (
    ReadFileSkill,
    WriteFileSkill,
    EditFileSkill,
    RunBashCommandSkill,
    ListDirSkill,
    GrepSearchSkill
)
from pico.mcp_host import MCPHost, PermissionLevel


@pytest.fixture
def temp_test_file(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("def hello():\n    print('Hello World')\n    return 42\n")
    return str(f)


def test_read_file_full_and_sliced(temp_test_file):
    reader = ReadFileSkill()
    res = reader.execute({"path": temp_test_file})
    assert res.success is True
    assert "1: def hello():" in res.output["content"]
    assert res.output["total_lines"] == 3

    # Slice lines 2 to 3
    res_sliced = reader.execute({"path": temp_test_file, "start_line": 2, "end_line": 3})
    assert res_sliced.success is True
    assert "2:     print('Hello World')" in res_sliced.output["content"]
    assert "1: def hello():" not in res_sliced.output["content"]


def test_write_and_edit_file(tmp_path):
    target_path = str(tmp_path / "sub" / "new_file.txt")
    writer = WriteFileSkill()
    editor = EditFileSkill()

    # Write file
    w_res = writer.execute({"path": target_path, "content": "alpha beta gamma\n"})
    assert w_res.success is True
    assert os.path.exists(target_path)

    # Edit file
    e_res = editor.execute({"path": target_path, "target": "beta", "replacement": "OMEGA"})
    assert e_res.success is True
    assert e_res.output["replacements_made"] == 1

    with open(target_path) as f:
        assert f.read() == "alpha OMEGA gamma\n"


def test_run_bash_command_and_safety():
    runner = RunBashCommandSkill()
    # Safe echo command
    res = runner.execute({"command": "echo 'Pico Agent Live'"})
    assert res.success is True
    assert res.output["stdout"] == "Pico Agent Live"
    assert res.output["returncode"] == 0

    # Banned dangerous command
    bad_res = runner.execute({"command": "withdraw_crypto all"})
    assert bad_res.success is False
    assert "permanently BLOCKED" in bad_res.error


def test_list_dir_and_grep(tmp_path):
    (tmp_path / "file1.txt").write_text("apple banana\n")
    (tmp_path / "file2.py").write_text("cat dog elephant\n")

    lister = ListDirSkill()
    res = lister.execute({"path": str(tmp_path)})
    assert res.success is True
    assert res.output["total_items"] >= 2

    grepper = GrepSearchSkill()
    grep_res = grepper.execute({"path": str(tmp_path), "pattern": "elephant"})
    assert grep_res.success is True
    assert grep_res.output["match_count"] >= 1
    assert "file2.py" in grep_res.output["matches"]


def test_mcp_host_integration_with_coding_tools(tmp_path):
    host = MCPHost()
    sample_file = str(tmp_path / "mcp_test.txt")

    # Write via MCP Host (ASK level requires user_approved=True)
    unapproved_ok, unapproved_msg, meta = host.execute_tool(
        "write_file",
        {"path": sample_file, "content": "hello from mcp\n"},
        user_approved=False
    )
    assert unapproved_ok is False
    assert meta.get("approval_required") is True

    # Approved write
    approved_ok, approved_msg, _ = host.execute_tool(
        "write_file",
        {"path": sample_file, "content": "hello from mcp\n"},
        user_approved=True
    )
    assert approved_ok is True

    # Read via MCP Host (SEE level runs freely)
    read_ok, content, _ = host.execute_tool("read_file", {"path": sample_file})
    assert read_ok is True
    assert "hello from mcp" in content
