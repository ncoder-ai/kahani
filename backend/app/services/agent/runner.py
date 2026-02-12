"""Core agent loop implementing the ReAct pattern.

The runner orchestrates: LLM call → parse → tool execution → observation → repeat.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .react_parser import ParsedStep, parse_react_output
from .tool import Tool
from .trace_logger import AgentTraceLogger

logger = logging.getLogger(__name__)

# Maximum chars per tool observation to prevent context overflow
OBSERVATION_MAX_CHARS = 6000


class AgentRunner:
    """Execute a ReAct agent loop with tools."""

    def __init__(
        self,
        extraction_service,
        tools: List[Tool],
        system_prompt: str,
        max_turns: int = 8,
        timeout: float = 45.0,
        agent_name: str = "agent",
        trace_logger: Optional[AgentTraceLogger] = None,
        allow_thinking: bool = False,
    ):
        self.extraction_service = extraction_service
        self.tools = {t.name: t for t in tools}
        self.system_prompt = self._build_system_prompt(system_prompt, tools)
        self.max_turns = max_turns
        self.timeout = timeout
        self.agent_name = agent_name
        self.trace_logger = trace_logger
        self.allow_thinking = allow_thinking

    def _build_system_prompt(self, base_prompt: str, tools: List[Tool]) -> str:
        """Append tool descriptions to the system prompt."""
        tool_block = "\n\nAvailable tools:\n" + "\n\n".join(
            t.format_for_prompt() for t in tools
        )
        return base_prompt + tool_block

    async def run(self, user_message: str) -> Dict[str, Any]:
        """Run the agent loop until Final Answer or limits hit.

        Returns:
            {
                "answer": Any,       # Parsed final answer (dict/list/str)
                "turns": int,        # Number of LLM calls made
                "trace": list,       # Per-turn trace records
                "success": bool,     # Whether agent produced a final answer
                "error": str | None  # Error message if failed
            }
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]
        trace = []
        start_time = time.monotonic()

        for turn in range(self.max_turns):
            elapsed = time.monotonic() - start_time
            if elapsed > self.timeout:
                error = f"Agent timed out after {elapsed:.1f}s ({turn} turns)"
                logger.warning(f"[{self.agent_name}] {error}")
                if self.trace_logger:
                    self.trace_logger.log(f"[TIMEOUT] {error}", trace, None)
                return self._result(None, turn, trace, False, error)

            # Call LLM
            try:
                remaining = self.timeout - elapsed
                response_text = await asyncio.wait_for(
                    self.extraction_service.generate_with_messages(
                        messages, allow_thinking=self.allow_thinking
                    ),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                error = f"LLM call timed out (turn {turn + 1})"
                logger.warning(f"[{self.agent_name}] {error}")
                if self.trace_logger:
                    self.trace_logger.log(f"[TIMEOUT] {error}", trace, None)
                return self._result(None, turn + 1, trace, False, error)
            except Exception as e:
                error = f"LLM call failed: {e}"
                logger.error(f"[{self.agent_name}] {error}")
                if self.trace_logger:
                    self.trace_logger.log(f"[ERROR] {error}", trace, None)
                return self._result(None, turn + 1, trace, False, error)

            # Parse ReAct output
            step = parse_react_output(response_text)
            turn_record = {
                "turn": turn + 1,
                "thought": step.thought,
                "action": step.action,
                "action_input": step.action_input,
                "raw_response": response_text,
            }

            # Final Answer — we're done
            if step.final_answer is not None:
                turn_record["final_answer"] = step.final_answer
                trace.append(turn_record)
                logger.info(f"[{self.agent_name}] Completed in {turn + 1} turns")
                if self.trace_logger:
                    self.trace_logger.log(user_message, trace, step.final_answer)
                return self._result(step.final_answer, turn + 1, trace, True, None)

            # No action parsed — ask agent to try again
            if not step.action:
                observation = (
                    "Error: Could not parse your response. "
                    "Please use the exact format:\n"
                    "Thought: <your reasoning>\n"
                    "Action: <tool_name>\n"
                    "Action Input: {\"param\": \"value\"}\n\n"
                    "Or if you're done:\n"
                    "Thought: <your reasoning>\n"
                    "Final Answer: <your answer>"
                )
                turn_record["observation"] = observation
                trace.append(turn_record)
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": f"Observation: {observation}"})
                continue

            # Execute tool
            tool = self.tools.get(step.action)
            if not tool:
                observation = (
                    f"Error: Unknown tool '{step.action}'. "
                    f"Available tools: {', '.join(self.tools.keys())}"
                )
            else:
                try:
                    kwargs = step.action_input or {}
                    observation = await tool.func(**kwargs)
                    # Truncate long observations
                    if len(observation) > OBSERVATION_MAX_CHARS:
                        observation = observation[:OBSERVATION_MAX_CHARS] + "\n... (truncated)"
                except Exception as e:
                    observation = f"Error executing {step.action}: {e}"
                    logger.warning(f"[{self.agent_name}] Tool error: {e}")

            turn_record["observation"] = observation
            trace.append(turn_record)

            # Append assistant response + observation for next turn
            messages.append({"role": "assistant", "content": response_text})
            messages.append({"role": "user", "content": f"Observation: {observation}"})

        # Hit max turns
        error = f"Agent hit max turns ({self.max_turns})"
        logger.warning(f"[{self.agent_name}] {error}")
        if self.trace_logger:
            self.trace_logger.log(user_message, trace, None)
        return self._result(None, self.max_turns, trace, False, error)

    @staticmethod
    def _result(answer, turns, trace, success, error):
        return {
            "answer": answer,
            "turns": turns,
            "trace": trace,
            "success": success,
            "error": error,
        }
