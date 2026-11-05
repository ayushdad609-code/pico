"""
Tests for Pico's Autonomous ReAct Agent Loop Engine.
"""

import os
import pytest
from pico.agent_loop import AgentLoopEngine, ToolCall
from pico.onboarding import OnboardingFlow


def test_agent_loop_immediate_completion():
    engine = AgentLoopEngine()
    profile = OnboardingFlow.create_fast_path_profile("loop_test_1", "Ayush")

    # Mock model callable that completes immediately
    def mock_model(sys_prompt, messages):
        return "Everything looks great! No tools needed."

    result = engine.run_loop("Tell me a fun greeting", profile, mock_model)
    assert result.success is True
    assert result.total_steps == 1
    assert "Everything looks great" in result.final_output


def test_agent_loop_multi_step_tool_chaining(tmp_path):
    engine = AgentLoopEngine()
    profile = OnboardingFlow.create_fast_path_profile("loop_test_2", "Ayush")
    test_file = str(tmp_path / "agent_work.py")

    step_counter = {"count": 0}

    # Model simulates: 1. Write file -> 2. Read file to verify -> 3. Final answer
    def mock_model(sys_prompt, messages):
        step_counter["count"] += 1
        if step_counter["count"] == 1:
            return f'```json\n{{"thought": "Create helper file", "tool": "write_file", "args": {{"path": "{test_file}", "content": "x = 42\\n"}}}}\n```'
        elif step_counter["count"] == 2:
            return f'```json\n{{"thought": "Verify written file", "tool": "read_file", "args": {{"path": "{test_file}"}}}}\n```'
        else:
            return "Task completed: Created and verified agent_work.py with x = 42!"

    result = engine.run_loop(
        goal="Create agent_work.py with x=42 and verify it",
        profile=profile,
        model_callable=mock_model,
        pre_approved_tools=["write_file", "read_file"]
    )

    assert result.success is True
    assert result.total_steps == 3
    assert os.path.exists(test_file)
    with open(test_file) as f:
        assert "x = 42" in f.read()
    assert "Task completed" in result.final_output


def test_agent_loop_pauses_on_unapproved_ask_tool(tmp_path):
    engine = AgentLoopEngine()
    profile = OnboardingFlow.create_fast_path_profile("loop_test_3", "Ayush")
    test_file = str(tmp_path / "unapproved.txt")

    def mock_model(sys_prompt, messages):
        return f'```json\n{{"thought": "Try writing without approval", "tool": "write_file", "args": {{"path": "{test_file}", "content": "secret"}}}}\n```'

    result = engine.run_loop(
        goal="Write unapproved file",
        profile=profile,
        model_callable=mock_model,
        pre_approved_tools=[]  # No pre-approvals
    )

    assert result.paused_for_approval is True
    assert result.pending_approval is not None
    assert result.pending_approval["tool_name"] == "write_file"
    assert not os.path.exists(test_file)


def test_agent_loop_cycle_detection():
    engine = AgentLoopEngine()
    profile = OnboardingFlow.create_fast_path_profile("loop_test_4", "Ayush")

    # Model repeats the same failing read call
    def mock_model(sys_prompt, messages):
        return '```json\n{"thought": "Read non-existent file", "tool": "read_file", "args": {"path": "/fake/path/missing.txt"}}\n```'

    result = engine.run_loop(
        goal="Keep trying to read bad file",
        profile=profile,
        model_callable=mock_model,
        max_steps=4
    )

    # Engine caught repeating call and injected warning
    warnings = [s for s in result.steps if s.observation and "AGENT LOOP WARNING" in s.observation]
    assert len(warnings) > 0
