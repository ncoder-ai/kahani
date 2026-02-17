"""Tool definition schema for the agent framework.

Tools are the bridge between an agent's text-based reasoning and your internal APIs.
The LLM never sees Python code — it only sees the text descriptions rendered by format_for_prompt().
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, List, Optional


@dataclass
class ToolParameter:
    """A single parameter that a tool accepts."""
    name: str
    type: str  # "string", "int", "list[string]", etc.
    description: str
    required: bool = True
    default: Any = None


@dataclass
class Tool:
    """An agent tool: a named function with a text description the LLM can read."""
    name: str
    description: str
    parameters: List[ToolParameter]
    func: Callable[..., Coroutine[Any, Any, str]]  # async (kwargs) -> str

    def format_for_prompt(self) -> str:
        """Render this tool as text for the agent's system prompt."""
        lines = [f"  {self.name}: {self.description}"]
        if self.parameters:
            lines.append("    Parameters:")
            for p in self.parameters:
                req = "required" if p.required else f"optional, default={p.default}"
                lines.append(f"      - {p.name} ({p.type}, {req}): {p.description}")
        return "\n".join(lines)
