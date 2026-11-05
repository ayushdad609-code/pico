"""
Autonomous Multi-Turn ReAct Agent Loop Engine for Pico.
Provides Claude Code-grade autonomous tool-use, multi-step problem solving,
and cycle-prevention for coding, terminal, and device automation.
"""

import os
import re
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Callable

from pico.mcp_host import MCPHost, PermissionLevel
from pico.models import UserProfile
from pico.device import DeviceProfiler, DeviceTier

logger = logging.getLogger("pico.agent_loop")


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]
    call_id: str = ""


@dataclass
class AgentStep:
    step_number: int
    thought: str
    tool_call: Optional[ToolCall] = None
    observation: Optional[str] = None
    output_text: Optional[str] = None
    approval_required: bool = False
    approval_details: Optional[Dict[str, Any]] = None


@dataclass
class AgentRunResult:
    goal: str
    final_output: str
    steps: List[AgentStep]
    total_steps: int
    success: bool
    paused_for_approval: bool = False
    pending_approval: Optional[Dict[str, Any]] = None
    distilled_skill: Optional[Dict[str, Any]] = None
    execution_time_ms: float = 0.0


class AgentLoopEngine:
    """
    Autonomous ReAct execution loop for Pico.
    Orchestrates: Model Reasoning -> Tool Call -> Observation -> Next Step -> Finish.
    """

    def __init__(self, mcp_host: Optional[MCPHost] = None):
        self.mcp = mcp_host or MCPHost()

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns tool specs formatted for LLM system prompts."""
        definitions = []
        for name, tool in self.mcp.tools.items():
            definitions.append({
                "name": name,
                "description": tool.description,
                "permission": tool.permission_level.value,
                "parameters": tool.parameters
            })
        return definitions

    def format_tools_prompt(self) -> str:
        """Renders tool catalog into system prompt."""
        tools = self.get_tool_definitions()
        lines = [
            "### AVAILABLE AUTONOMOUS TOOLS:",
            "You can call tools to inspect files, write code, run shell commands, or check device sensors.",
            "To call a tool, respond strictly with a tool-call JSON block:",
            "```json",
            '{"thought": "Why I need this tool", "tool": "tool_name", "args": {"param1": "val1"}}',
            "```",
            "When the task is complete, do NOT output a tool JSON block. Just respond naturally with your final answer.",
            "",
            "Tools catalog:"
        ]
        for t in tools:
            lines.append(f"- **{t['name']}** [{t['permission']}]: {t['description']}")
            if t['parameters']:
                lines.append(f"  Args: {json.dumps(t['parameters'])}")
        return "\n".join(lines)

    def parse_model_response(self, text: str) -> Tuple[Optional[str], Optional[ToolCall]]:
        """
        Parses model output to check if it's issuing a ToolCall or a Final Answer.
        Supports both raw JSON blocks and markdown code-fenced blocks.
        """
        text = text.strip()

        # Check for JSON block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        candidate = json_match.group(1) if json_match else None

        if not candidate and text.startswith("{") and text.endswith("}"):
            candidate = text

        if candidate:
            try:
                data = json.loads(candidate)
                if "tool" in data:
                    thought = data.get("thought", "")
                    tool_name = data.get("tool", "")
                    args = data.get("args", {})
                    if not isinstance(args, dict):
                        args = {}
                    return thought, ToolCall(name=tool_name, arguments=args)
            except Exception:
                pass

        # Also search for inline {"tool": ...}
        inline_match = re.search(r'\{\s*"tool"\s*:\s*"([a-zA-Z0-9_]+)"\s*,\s*"args"\s*:\s*(\{.*?\})\s*\}', text, re.DOTALL)
        if inline_match:
            try:
                tool_name = inline_match.group(1)
                args = json.loads(inline_match.group(2))
                return "", ToolCall(name=tool_name, arguments=args)
            except Exception:
                pass

        return None, None

    def execute_step(
        self,
        tool_call: ToolCall,
        user_approved: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Executes a single tool via MCPHost with permission checks."""
        return self.mcp.execute_tool(
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
            user_approved=user_approved
        )

    def run_loop(
        self,
        goal: str,
        profile: UserProfile,
        model_callable: Callable[[str, List[Dict[str, str]]], str],
        max_steps: int = 8,
        pre_approved_tools: Optional[List[str]] = None,
        auto_distill: bool = False
    ) -> AgentRunResult:
        """
        Executes the autonomous loop up to max_steps.
        model_callable: function(system_prompt, messages_history) -> model_response_str
        """
        start_t = time.time()
        steps: List[AgentStep] = []
        messages: List[Dict[str, str]] = [
            {"role": "user", "content": f"Task Goal: {goal}"}
        ]

        system_prompt = (
            f"You are Pico, an autonomous coding and device agent running on Android Termux for {profile.name}.\n"
            f"Persona: Childish & Kind, sharp engineering intelligence, careful with device resources.\n\n"
            f"{self.format_tools_prompt()}\n\n"
            "Think step-by-step. Break the goal down. Call tools to inspect and execute. Verify your work before concluding."
        )

        pre_approved = set(pre_approved_tools or [])
        recent_calls: List[Tuple[str, str]] = []

        for step_idx in range(1, max_steps + 1):
            # 1. Ask model for next action
            model_response = model_callable(system_prompt, messages)
            thought, tool_call = self.parse_model_response(model_response)

            # 2. If no tool call, task is complete!
            if not tool_call:
                final_step = AgentStep(
                    step_number=step_idx,
                    thought="Goal completed",
                    output_text=model_response
                )
                steps.append(final_step)

                # Hermes Autonomous Skill Distillation
                distilled = None
                if auto_distill and len(steps) >= 2:
                    distilled = self.distill_and_persist_skill(goal, steps, model_callable)

                return AgentRunResult(
                    goal=goal,
                    final_output=model_response,
                    steps=steps,
                    total_steps=len(steps),
                    success=True,
                    distilled_skill=distilled,
                    execution_time_ms=round((time.time() - start_t) * 1000, 2)
                )

            # 3. Cycle detection (repeating same failed call 3 times)
            call_sig = (tool_call.name, json.dumps(tool_call.arguments, sort_keys=True))
            if recent_calls.count(call_sig) >= 2:
                obs = f"[AGENT LOOP WARNING]: Tool '{tool_call.name}' called repeatedly with identical args. Change strategy."
                step_record = AgentStep(
                    step_number=step_idx,
                    thought=thought or "",
                    tool_call=tool_call,
                    observation=obs
                )
                steps.append(step_record)
                messages.append({"role": "assistant", "content": model_response})
                messages.append({"role": "user", "content": f"Observation: {obs}"})
                recent_calls.append(call_sig)
                continue

            recent_calls.append(call_sig)

            # 4. Check approval for ASK level
            auto_approve = (tool_call.name in pre_approved)
            success, output_data, meta = self.execute_step(tool_call, user_approved=auto_approve)

            if not success and meta.get("approval_required"):
                step_record = AgentStep(
                    step_number=step_idx,
                    thought=thought or "",
                    tool_call=tool_call,
                    approval_required=True,
                    approval_details=meta
                )
                steps.append(step_record)
                return AgentRunResult(
                    goal=goal,
                    final_output=f"I need your approval to {tool_call.name}.",
                    steps=steps,
                    total_steps=len(steps),
                    success=False,
                    paused_for_approval=True,
                    pending_approval=meta,
                    execution_time_ms=round((time.time() - start_t) * 1000, 2)
                )

            # 5. Record observation and continue
            obs = output_data if success else f"Error: {output_data}"
            step_record = AgentStep(
                step_number=step_idx,
                thought=thought or "",
                tool_call=tool_call,
                observation=obs
            )
            steps.append(step_record)

            messages.append({"role": "assistant", "content": model_response})
            messages.append({"role": "user", "content": f"Observation from {tool_call.name}:\n{obs}"})

        # Hit max steps without concluding
        return AgentRunResult(
            goal=goal,
            final_output=f"Reached step limit ({max_steps} steps). Here is what was completed so far.",
            steps=steps,
            total_steps=len(steps),
            success=False,
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )

    def distill_and_persist_skill(
        self,
        goal: str,
        steps: List[AgentStep],
        model_callable: Optional[Callable[[str, List[Dict[str, str]]], str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Hermes-style autonomous procedural skill distillation.
        Evaluates a successful multi-step execution and synthesizes a reusable skill.
        """
        if not model_callable or len(steps) < 2:
            return None

        # Filter for steps with tools
        tool_steps = [s for s in steps if s.tool_call]
        if not tool_steps:
            return None

        steps_summary = []
        for s in tool_steps:
            steps_summary.append(
                f"Step {s.step_number}: Tool '{s.tool_call.name}' with args {json.dumps(s.tool_call.arguments)} -> Observation: {str(s.observation)[:200]}"
            )

        distill_prompt = (
            "You are Pico's Hermes procedural skill distillation engine.\n"
            f"Task Goal: {goal}\n\n"
            "Execution Trace:\n" + "\n".join(steps_summary) + "\n\n"
            "Evaluate if this trace represents a generalizable, reusable multi-step procedure.\n"
            "If yes, respond strictly with a valid JSON block:\n"
            "```json\n"
            "{\n"
            '  "is_reusable": true,\n'
            '  "name": "snake_case_skill_name",\n'
            '  "description": "Clear explanation of what the reusable skill does",\n'
            '  "parameters_schema": {"param1": {"type": "string", "required": true, "description": "..."}},\n'
            '  "code": "Python code. Must either define execute(inputs: dict) -> dict OR class <Name>Skill(BaseSkill): ...",\n'
            '  "test_input": {"param1": "sample_val"}\n'
            "}\n"
            "```\n"
            'If this workflow is a one-off or not reusable, respond with: {"is_reusable": false}'
        )

        try:
            raw_response = model_callable(distill_prompt, [])
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
            candidate = json_match.group(1) if json_match else None
            if not candidate and raw_response.strip().startswith("{") and raw_response.strip().endswith("}"):
                candidate = raw_response.strip()

            if not candidate:
                return None

            data = json.loads(candidate)
            if not data.get("is_reusable") or not data.get("name") or not data.get("code"):
                return None

            from pico.skills.skill_manage import SkillManageSkill
            manager = SkillManageSkill()
            res = manager.execute({
                "action": "create",
                "name": data["name"],
                "description": data.get("description", ""),
                "parameters_schema": data.get("parameters_schema", {}),
                "code": data["code"],
                "test_input": data.get("test_input")
            })

            if res.success:
                logger.info(f"✨ Pico distilled and persisted new procedural skill '{data['name']}'!")
                return res.output
            else:
                logger.warning(f"Failed to persist distilled skill '{data.get('name')}': {res.error}")
                return None
        except Exception as e:
            logger.warning(f"Distillation exception: {e}")
            return None
