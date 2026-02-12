"""Parse ReAct-format output from LLM text.

ReAct format:
    Thought: <reasoning>
    Action: <tool_name>
    Action Input: <json params>

Or final answer:
    Thought: <reasoning>
    Final Answer: <json or text>
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedStep:
    """One parsed step from the agent's ReAct output."""
    thought: str = ""
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    final_answer: Optional[Any] = None
    raw_text: str = ""


def parse_react_output(text: str) -> ParsedStep:
    """Extract Thought / Action / Action Input / Final Answer from LLM text.

    Handles:
    - Multi-line thoughts
    - JSON with or without markdown fences
    - Extra whitespace and newlines
    - Malformed output (returns what it can parse)
    """
    step = ParsedStep(raw_text=text)
    if not text or not text.strip():
        return step

    text = text.strip()

    # Normalize markdown-decorated ReAct labels to plain format.
    # Small models often style them as bold (**Action:**) or headings (### Final Answer).

    # Strip bold markers around ReAct labels (requires bold marker at line start)
    text = re.sub(
        r"^(?:\*{1,2})(Action\s*Input|Final\s*Answer|Thought|Action)(?:\*{1,2})?:(?:\*{1,2})?",
        r"\1:",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    # Strip heading prefixes from standalone ReAct labels (### Final Answer)
    text = re.sub(
        r"^#{1,6}\s+(Action\s*Input|Final\s*Answer|Thought|Action)\s*:?(?=\s*$)",
        r"\1:",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    # All regexes use ^ with MULTILINE so "Action:" only matches at line start,
    # not inside prose like "the upcoming action:\n-"
    ML = re.MULTILINE | re.DOTALL | re.IGNORECASE

    # Extract Thought (everything between "Thought:" and next section)
    thought_match = re.search(
        r"^Thought:\s*(.*?)(?=\n\s*^(?:Action:|Final Answer:)|\Z)",
        text, ML
    )
    if thought_match:
        step.thought = thought_match.group(1).strip()

    # Check for Final Answer first (takes priority)
    final_match = re.search(
        r"^Final Answer:\s*(.*)",
        text, ML
    )
    if final_match:
        raw_answer = final_match.group(1).strip()
        step.final_answer = _try_parse_json(raw_answer)
        return step

    # Extract Action name — only match first occurrence at start of line
    action_match = re.search(
        r"^Action:\s*(\S+)",
        text, re.MULTILINE | re.IGNORECASE
    )
    if action_match:
        step.action = action_match.group(1).strip()

    # Extract Action Input (JSON block after "Action Input:" at start of line)
    # Only capture up to the next start-of-line section marker or end of string.
    # Use \Z (absolute end of string) not $ (end of line in MULTILINE mode)
    # to ensure multi-line JSON blocks are fully captured.
    input_match = re.search(
        r"^Action Input:\s*(.*?)(?=\n\s*^(?:Thought:|Action:|Final Answer:)|\Z)",
        text, ML
    )
    if input_match:
        raw_input = input_match.group(1).strip()
        parsed = _try_parse_json(raw_input)
        if isinstance(parsed, dict):
            step.action_input = parsed
        else:
            # If it's a plain string, wrap as {"query": value}
            step.action_input = {"query": str(parsed)} if parsed else {}

    return step


def _try_parse_json(text: str) -> Any:
    """Try to parse JSON from text, stripping markdown fences and extra content."""
    if not text:
        return text

    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting the first JSON object/array via brace matching
    for opener, closer in [("{", "}"), ("[", "]")]:
        start = cleaned.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start:i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break

    # Return as-is if not JSON
    return cleaned
