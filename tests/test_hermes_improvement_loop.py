"""
Comprehensive Test Suite for Hermes Agent-Inspired Self-Improvement Loop for Pico.
Tests:
1. All 6 actions of skill_manage (create, read, update, test, rollback, deprecate).
2. Security policy rejection on disallowed patterns.
3. SQLite FTS5 BM25 ranked search & cross-session recall.
4. Honcho Dialectic User Model evolution (Thesis -> Antithesis -> Synthesis).
5. Autonomous post-task skill distillation in AgentLoopEngine.
6. HermesMemoryCurator reflection and periodic nudges.
7. Zero token inflation verification.
"""

import os
import shutil
import pytest
from datetime import datetime, timezone

from pico.models import UserProfile, Fact, FactStatus, FactSource, Sensitivity
from pico.memory import MemoryStore
from pico.hermes_memory import HermesMemoryCoordinator, HermesMemoryPack
from pico.hermes_curator import HermesMemoryCurator
from pico.skills.registry import SkillRegistry
from pico.skills.skill_manage import (
    SkillManageSkill,
    CUSTOM_SKILLS_DIR,
    DEPRECATED_SKILLS_DIR
)
from pico.skills.base_skill import BaseSkill, SkillResult
from pico.agent_loop import AgentLoopEngine, AgentStep, ToolCall


@pytest.fixture(autouse=True)
def cleanup_custom_skills():
    """Ensure clean custom and deprecated directories before and after tests."""
    yield
    test_skill_names = ["temp_test_math", "temp_distilled_calc", "evil_skill"]
    for name in test_skill_names:
        for ext in [".py", ".py.bak"]:
            p = os.path.join(CUSTOM_SKILLS_DIR, f"{name}{ext}")
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
            dep_p = os.path.join(DEPRECATED_SKILLS_DIR, f"{name}{ext}")
            if os.path.exists(dep_p):
                try:
                    os.remove(dep_p)
                except Exception:
                    pass


# =============================================================================
# 1. TEST THE 6 ACTIONS OF skill_manage
# =============================================================================
def test_skill_manage_create_and_read():
    registry = SkillRegistry()
    manager = SkillManageSkill(registry=registry)

    skill_code = '''
def execute(inputs):
    a = inputs.get("a", 0)
    b = inputs.get("b", 0)
    return {"sum": a + b, "product": a * b}
'''
    # Action 1: Create
    res_create = manager.execute({
        "action": "create",
        "name": "temp_test_math",
        "description": "Calculates sum and product of two numbers",
        "parameters_schema": {"a": {"type": "number"}, "b": {"type": "number"}},
        "code": skill_code,
        "test_input": {"a": 3, "b": 7}
    })

    assert res_create.success is True
    assert res_create.output["action"] == "create"
    assert res_create.output["name"] == "temp_test_math"
    assert os.path.exists(os.path.join(CUSTOM_SKILLS_DIR, "temp_test_math.py"))

    # Verify registered and callable
    skill = registry.get_skill("temp_test_math")
    assert skill is not None
    exec_res = registry.execute_skill("temp_test_math", {"a": 5, "b": 4})
    assert exec_res.success is True
    assert exec_res.output["sum"] == 9
    assert exec_res.output["product"] == 20

    # Action 2: Read
    res_read = manager.execute({
        "action": "read",
        "name": "temp_test_math"
    })
    assert res_read.success is True
    assert res_read.output["action"] == "read"
    assert "sum" in res_read.output["code"]
    assert res_read.output["is_custom"] is True


def test_skill_manage_update_and_test():
    registry = SkillRegistry()
    manager = SkillManageSkill(registry=registry)

    # Initial creation
    initial_code = '''
def execute(inputs):
    x = inputs.get("x", 0)
    return {"result": x * 2}
'''
    res_create = manager.execute({
        "action": "create",
        "name": "temp_test_math",
        "description": "Doubles a number",
        "code": initial_code,
        "test_input": {"x": 5}
    })
    assert res_create.success is True

    # Action 4: Test standalone code without saving
    test_code = '''
def execute(inputs):
    return {"val": inputs.get("v") ** 2}
'''
    res_test = manager.execute({
        "action": "test",
        "code": test_code,
        "test_input": {"v": 4}
    })
    assert res_test.success is True
    assert res_test.output["output"]["val"] == 16

    # Action 3: Update existing skill with backup
    updated_code = '''
def execute(inputs):
    x = inputs.get("x", 0)
    return {"result": x * 10}
'''
    res_update = manager.execute({
        "action": "update",
        "name": "temp_test_math",
        "code": updated_code,
        "test_input": {"x": 2}
    })
    assert res_update.success is True
    assert res_update.output["action"] == "update"
    assert os.path.exists(os.path.join(CUSTOM_SKILLS_DIR, "temp_test_math.py.bak"))

    # Test updated behavior
    exec_res = registry.execute_skill("temp_test_math", {"x": 3})
    assert exec_res.success is True
    assert exec_res.output["result"] == 30


def test_skill_manage_rollback_and_deprecate():
    registry = SkillRegistry()
    manager = SkillManageSkill(registry=registry)

    v1_code = '''
def execute(inputs):
    return {"version": "v1"}
'''
    manager.execute({
        "action": "create",
        "name": "temp_test_math",
        "code": v1_code,
        "test_input": {}
    })

    v2_code = '''
def execute(inputs):
    return {"version": "v2"}
'''
    manager.execute({
        "action": "update",
        "name": "temp_test_math",
        "code": v2_code,
        "test_input": {}
    })

    # Verify v2 active
    assert registry.execute_skill("temp_test_math", {}).output["version"] == "v2"

    # Action 5: Rollback
    res_rollback = manager.execute({
        "action": "rollback",
        "name": "temp_test_math"
    })
    assert res_rollback.success is True
    assert res_rollback.output["status"] == "rolled_back"

    # Verify rolled back to v1
    assert registry.execute_skill("temp_test_math", {}).output["version"] == "v1"

    # Action 6: Deprecate
    res_dep = manager.execute({
        "action": "deprecate",
        "name": "temp_test_math",
        "reason": "Replaced by built-in"
    })
    assert res_dep.success is True
    assert res_dep.output["status"] == "deprecated"
    assert registry.get_skill("temp_test_math") is None
    assert os.path.exists(os.path.join(DEPRECATED_SKILLS_DIR, "temp_test_math.py"))


def test_skill_manage_security_rejection():
    registry = SkillRegistry()
    manager = SkillManageSkill(registry=registry)

    malicious_codes = [
        'import os\nos.system("rm -rf /")',
        'import subprocess\nsubprocess.call(["format", "c:"])',
        'def execute(inputs):\n    transfer_funds(amount=1000)',
    ]

    for bad_code in malicious_codes:
        res = manager.execute({
            "action": "create",
            "name": "evil_skill",
            "code": bad_code,
            "test_input": {}
        })
        assert res.success is False
        assert "policy" in res.error.lower() or "forbidden" in res.error.lower()
        assert not os.path.exists(os.path.join(CUSTOM_SKILLS_DIR, "evil_skill.py"))


# =============================================================================
# 2. TEST SQLITE FTS5 BM25 SEARCH & CROSS-SESSION RECALL
# =============================================================================
def test_sqlite_fts5_cross_session_recall():
    memory = MemoryStore(":memory:")
    coordinator = HermesMemoryCoordinator(memory)

    user_id = "test_user_fts"

    # Index 3 distinct historical turns
    coordinator.index_session_turn(
        session_id="sess_101",
        user_id=user_id,
        user_prompt="How do I configure git proxy on Termux?",
        agent_response="Set git config --global http.proxy http://127.0.0.1:8080",
        learnings="Git proxy setup on Termux localhost",
        tags="git termux proxy"
    )
    coordinator.index_session_turn(
        session_id="sess_102",
        user_id=user_id,
        user_prompt="What is my daily protein target?",
        agent_response="Your daily target is 140g based on 70kg weight.",
        learnings="Protein target 140g",
        tags="nutrition gym fitness"
    )
    coordinator.index_session_turn(
        session_id="sess_103",
        user_id=user_id,
        user_prompt="Fix the timeout in router.py",
        agent_response="Adjusted socket timeout to 5000ms in router connection.",
        learnings="Socket timeout fix in router",
        tags="coding bugfix router"
    )

    # Search for git proxy
    matches = coordinator.search_cross_session(user_id=user_id, query="git proxy config", limit=2)
    assert len(matches) >= 1
    top_match = matches[0]
    assert top_match.session_id == "sess_101"
    assert "proxy" in top_match.user_prompt.lower()

    # Search for protein target
    matches_nutr = coordinator.search_cross_session(user_id=user_id, query="protein intake target", limit=1)
    assert len(matches_nutr) == 1
    assert matches_nutr[0].session_id == "sess_102"

    # Generate summary bridge
    summary_bridge = coordinator.summarize_past_context(matches)
    assert "[CROSS-SESSION RECALL" in summary_bridge
    assert "Git proxy" in summary_bridge
    # Verify zero token inflation (under 80 words)
    assert len(summary_bridge.split()) < 80


# =============================================================================
# 3. TEST HONCHO DIALECTIC USER MODEL EVOLUTION
# =============================================================================
def test_honcho_dialectic_model_evolution():
    memory = MemoryStore(":memory:")
    coordinator = HermesMemoryCoordinator(memory)

    profile = UserProfile(
        user_id="user_dialectic_test",
        name="Ayush",
        goal_90d="Launch companion app"
    )

    # 1. Initial thesis seeding
    model_v1 = coordinator.get_or_create_dialectic_model(profile.user_id, profile)
    assert "Ayush" in model_v1.thesis
    assert "Launch companion app" in model_v1.goals_context

    # 2. Dialectic evolution 1: New observation
    obs1 = "Prefers Python scripts with strict type hints over bash commands."
    model_v2 = coordinator.update_dialectic_model(profile.user_id, obs1)

    assert model_v2.thesis == model_v1.synthesis  # Old synthesis became new thesis
    assert model_v2.antithesis == obs1
    assert "type hints" in model_v2.synthesis

    # 3. Dialectic evolution 2: Second observation
    obs2 = "Working hours confirmed between 09:00 and 13:00 IST."
    model_v3 = coordinator.update_dialectic_model(profile.user_id, obs2)

    assert model_v3.thesis == model_v2.synthesis
    assert model_v3.antithesis == obs2
    assert "09:00" in model_v3.synthesis


# =============================================================================
# 4. TEST AUTONOMOUS POST-TASK SKILL DISTILLATION
# =============================================================================
def test_autonomous_skill_distillation():
    engine = AgentLoopEngine()

    steps = [
        AgentStep(
            step_number=1,
            thought="Check file",
            tool_call=ToolCall(name="read_file", arguments={"path": "calc.py"}),
            observation="file contains add(a, b)"
        ),
        AgentStep(
            step_number=2,
            thought="Calculate result",
            tool_call=ToolCall(name="run_command", arguments={"command": "python -c 'print(40 + 2)'"}),
            observation="42"
        )
    ]

    mock_llm_json = '''
```json
{
  "is_reusable": true,
  "name": "temp_distilled_calc",
  "description": "Adds 42 offset to numbers",
  "parameters_schema": {"val": {"type": "number", "required": true}},
  "code": "def execute(inputs):\\n    v = inputs.get('val', 0)\\n    return {'result': v + 42}",
  "test_input": {"val": 10}
}
```
'''
    def mock_callable(prompt, messages):
        return mock_llm_json

    # 1. Gated Consent Check (§g / C2): Model cannot self-modify without user approval
    gated_result = engine.distill_and_persist_skill(
        goal="Calculate 42 offset repeatedly",
        steps=steps,
        model_callable=mock_callable,
        user_approved=False
    )
    assert gated_result is not None
    assert gated_result["name"] == "temp_distilled_calc"
    assert gated_result["status"] == "APPROVAL_REQUIRED"

    # 2. Approved Execution: Once human approves the card, code is created & hot-loaded
    result = engine.distill_and_persist_skill(
        goal="Calculate 42 offset repeatedly",
        steps=steps,
        model_callable=mock_callable,
        user_approved=True
    )

    assert result is not None
    assert result["name"] == "temp_distilled_calc"
    assert result["status"] == "created"

    # Verify distilled skill executes in registry
    reg = SkillRegistry.get_shared_instance()
    skill_out = reg.execute_skill("temp_distilled_calc", {"val": 8})
    assert skill_out.success is True
    assert skill_out.output["result"] == 50


# =============================================================================
# 5. TEST HERMES MEMORY CURATOR & PERIODIC NUDGES
# =============================================================================
def test_hermes_memory_curator_and_nudges():
    memory = MemoryStore(":memory:")
    coordinator = HermesMemoryCoordinator(memory)
    curator = HermesMemoryCurator(coordinator, memory)

    user_id = "user_curator_test"

    # Reflection turn 1: User declares a preference
    prompt1 = "I prefer dark mode in all UI outputs and I am building an autonomous assistant"
    resp1 = "Understood! I have set dark mode as your default aesthetic."

    res1 = curator.reflect_and_curate(
        user_id=user_id,
        prompt=prompt1,
        agent_response=resp1,
        session_id="sess_cur_1"
    )

    assert res1["turn"] == 1
    assert res1["facts_extracted"] >= 1

    # Verify fact stored in memory
    facts = memory.get_what_i_know(user_id)
    assert any("dark mode" in str(f.get("value", "")).lower() for f in facts)

    # Force nudge check
    profile = UserProfile(user_id=user_id, name="Ayush")
    nudge = curator.check_and_generate_nudge(user_id, profile, force=True)
    assert nudge is not None
    assert "Pico" in nudge
