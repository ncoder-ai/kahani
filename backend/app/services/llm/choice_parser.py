"""
Choice Parser Module

Provides functions to parse and extract story choices from LLM responses.
Handles various JSON formats, incomplete responses, and uses regex fallbacks.
"""

import re
import json
import logging
from typing import Optional, List, Tuple, Any

logger = logging.getLogger(__name__)


def fix_incomplete_json_array(json_str: str) -> Optional[str]:
    """
    Attempt to fix an incomplete JSON array by extracting valid complete entries.
    Returns fixed JSON string or None if fixing is not possible.
    """
    if not json_str or not json_str.strip().startswith('['):
        return None

    try:
        # Remove the opening bracket
        content = json_str.lstrip('[').strip()

        # Try to extract complete string entries
        # Pattern: "..." followed by comma or end
        entries = []
        in_string = False
        escaped = False
        start_pos = None

        i = 0
        while i < len(content):
            char = content[i]

            if escaped:
                escaped = False
                i += 1
                continue

            if char == '\\':
                escaped = True
                i += 1
                continue

            if char == '"':
                if not in_string:
                    # Start of a new string
                    in_string = True
                    start_pos = i
                else:
                    # End of string - check if it's followed by comma or whitespace
                    end_pos = i + 1
                    # Look ahead for comma or end of content
                    remaining = content[end_pos:].lstrip()
                    if not remaining or remaining.startswith(',') or remaining.startswith(']'):
                        # This is a complete string entry
                        entry = content[start_pos:end_pos]
                        entries.append(entry)
                        in_string = False
                        # Skip past comma if present
                        if remaining.startswith(','):
                            i = end_pos + remaining.find(',') + 1
                            continue
                        elif remaining.startswith(']'):
                            break
                i += 1
                continue

            i += 1

        # If we found any complete entries, reconstruct the JSON array
        if entries:
            fixed_json = '[' + ', '.join(entries) + ']'
            logger.debug(f"[CHOICES PARSE] Fixed incomplete JSON: extracted {len(entries)} complete entries")
            return fixed_json

        # Fallback: try to close the last incomplete string if we're in one
        if in_string and start_pos is not None:
            # Close the current string
            incomplete_entry = content[start_pos:] + '"'
            # Remove trailing comma if present
            incomplete_entry = re.sub(r',\s*$', '', incomplete_entry)
            fixed_json = '[' + incomplete_entry + ']'
            logger.debug(f"[CHOICES PARSE] Fixed incomplete JSON: closed last string")
            return fixed_json

        return None
    except Exception as e:
        logger.warning(f"[CHOICES PARSE] Error fixing incomplete JSON: {e}")
        return None


def fix_malformed_json_escaping(text: str) -> str:
    """
    Fix common LLM JSON escaping issues:
    - Mixed quote escaping like \"' or \'
    - Double-escaped quotes like \\"
    - Unescaped quotes inside strings
    """
    # Fix patterns like \"' (escaped double quote followed by single quote)
    text = re.sub(r'\\"\'', '"', text)
    text = re.sub(r'\'\"', '"', text)
    # Fix escaped single quotes that shouldn't be escaped in JSON
    text = re.sub(r"\\\'", "'", text)
    # Fix double-escaped quotes
    text = re.sub(r'\\\\\"', '\\"', text)
    # Fix patterns like \'' (escaped single quote followed by single quote)
    text = re.sub(r"\\''", "'", text)
    return text


def fix_single_quotes_to_double(text: str) -> str:
    """
    Convert single-quoted JSON array to double-quoted.
    Handles cases where LLM outputs ['choice1', 'choice2'] instead of ["choice1", "choice2"].
    """
    # Only apply if it looks like a single-quoted array
    if not re.search(r"\[\s*'", text):
        return text

    # Simple state machine to convert single quotes to double quotes
    # while preserving single quotes inside strings
    result = []
    in_string = False
    string_char = None
    i = 0

    while i < len(text):
        char = text[i]

        # Handle escape sequences
        if i > 0 and text[i-1] == '\\':
            result.append(char)
            i += 1
            continue

        if not in_string:
            if char == "'":
                # Starting a string with single quote - convert to double
                result.append('"')
                in_string = True
                string_char = "'"
            elif char == '"':
                result.append(char)
                in_string = True
                string_char = '"'
            else:
                result.append(char)
        else:
            if char == string_char:
                # End of string
                if string_char == "'":
                    result.append('"')
                else:
                    result.append(char)
                in_string = False
                string_char = None
            elif char == '"' and string_char == "'":
                # Double quote inside single-quoted string - escape it
                result.append('\\"')
            else:
                result.append(char)

        i += 1

    return ''.join(result)


def extract_choices_with_regex(text: str) -> Optional[List[str]]:
    """
    Fallback method to extract choices using regex when JSON parsing fails.
    Looks for quoted strings that appear to be choices.
    Handles escaped quotes (\\") inside strings.
    """
    choices = []

    # First try double-quoted strings, handling escaped quotes
    # Pattern: (?:[^"\\]|\\.) matches either:
    #   - [^"\\] = any char except quote or backslash
    #   - \\. = backslash followed by any char (escaped char like \")
    # Minimum 10 chars, no maximum limit
    double_quoted = re.findall(r'"((?:[^"\\]|\\.){10,})"', text)
    for match in double_quoted:
        # Unescape: convert \" to " and \' to '
        cleaned = match.replace('\\"', '"').replace("\\'", "'").strip()
        # Filter out things that look like JSON keys or formatting
        if cleaned and not cleaned.startswith('{') and not cleaned.endswith(':') and 'choices' not in cleaned.lower():
            choices.append(cleaned)

    # If we didn't get enough, try single-quoted strings
    if len(choices) < 2:
        single_quoted = re.findall(r"'((?:[^'\\]|\\.){10,})'", text)
        for match in single_quoted:
            cleaned = match.replace('\\"', '"').replace("\\'", "'").strip()
            if cleaned and cleaned not in choices and not cleaned.startswith('{'):
                choices.append(cleaned)

    if len(choices) >= 2:
        logger.debug(f"[CHOICES PARSE] Regex fallback extracted {len(choices)} choices")
        return choices[:6]  # Limit to reasonable number

    return None


def _split_mixed_quote_choice(choice: str) -> List[str]:
    """
    Split a choice that contains embedded array element boundaries from mixed quotes.

    LLMs sometimes mix single and double quotes in JSON arrays, causing the JSON
    parser to merge multiple choices into one. E.g.:
      "Choice A.', 'Choice B.', 'Choice C."
    parses as a single string but actually contains 3 choices separated by ', '

    Only splits on sentence-ending patterns (period/punctuation + quote boundary)
    to avoid splitting on apostrophes like "Nishant's".
    """
    # Pattern: sentence-ending punctuation followed by quote-comma-quote boundary
    # Matches: .', ' or !', ' or ?', ' (sentence end → element boundary)
    parts = re.split(r"""(?<=[.!?])['"]\s*,\s*['"]""", choice)
    if len(parts) > 1:
        # Clean up: first part may have trailing quote, last may have leading quote
        cleaned = [p.strip().strip("'\"").strip() for p in parts]
        cleaned = [p for p in cleaned if len(p) > 5]
        if len(cleaned) > 1:
            logger.debug(f"[CHOICES PARSE] Split mixed-quote choice into {len(cleaned)} parts")
            return cleaned
    return [choice]


def _validate_and_return_choices(choices: Any) -> Optional[List[str]]:
    """Validate parsed choices and return cleaned list"""
    if isinstance(choices, list) and len(choices) >= 2:
        # Clean and validate each choice, splitting any that contain mixed-quote boundaries
        cleaned_choices = []
        for i, choice in enumerate(choices):
            if isinstance(choice, str):
                cleaned = choice.strip()
                # Remove any leading/trailing quotes that might have been double-escaped
                cleaned = cleaned.strip('"\'')
                if len(cleaned) > 5:  # Minimum reasonable choice length
                    # Check for mixed-quote boundaries inside this choice
                    sub_choices = _split_mixed_quote_choice(cleaned)
                    cleaned_choices.extend(sub_choices)
                else:
                    logger.debug(f"[CHOICES PARSE] Choice {i+1} too short: {len(cleaned)} chars")
            else:
                logger.debug(f"[CHOICES PARSE] Choice {i+1} not a string: {type(choice)}")

        if len(cleaned_choices) >= 2:
            logger.debug(f"[CHOICES PARSE] Successfully parsed {len(cleaned_choices)} choices")
            return cleaned_choices
        else:
            logger.warning(f"[CHOICES PARSE] Not enough valid choices: {len(cleaned_choices)} < 2")
    else:
        logger.warning(f"[CHOICES PARSE] Invalid format: got {type(choices)}, length: {len(choices) if isinstance(choices, list) else 'N/A'}")
    return None


def parse_choices_from_json(text: str) -> Optional[List[str]]:
    """
    Parse choices from JSON array string.
    Handles various formats and extracts valid choices.
    Returns None if parsing fails.
    """
    if not text or not text.strip():
        logger.warning("[CHOICES PARSE] Empty text provided")
        return None

    try:
        # Clean the text - remove any markdown code blocks
        original_text = text
        text = text.strip()

        # Handle markdown code blocks (```json ... ``` or ``` ... ```)
        # Improved markdown removal that handles various formats
        if '```' in text:
            # Strategy 1: Use regex to extract content between code block markers
            # This handles both ```json and ``` markers
            code_block_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
            if code_block_match:
                # Extract content from inside code blocks
                cleaned_text = code_block_match.group(1).strip()
                logger.debug(f"[CHOICES PARSE] Extracted content from markdown code block, length: {len(cleaned_text)}")
            else:
                # Fallback: Remove lines that are just ``` markers
                lines = text.split('\n')
                filtered_lines = []
                inside_code_block = False
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith('```'):
                        inside_code_block = not inside_code_block
                        continue  # Skip the marker line
                    # Add line if we're inside a code block (content) or outside (no code blocks)
                    # But if we're inside, we want the content
                    if inside_code_block or not any('```' in l for l in lines):
                        filtered_lines.append(line)
                cleaned_text = '\n'.join(filtered_lines).strip()

                # Strategy 2: If that didn't work, try regex removal of markers
                if '```' in cleaned_text:
                    # Remove any remaining ``` markers
                    cleaned_text = re.sub(r'```[a-z]*\s*\n?', '', cleaned_text, flags=re.IGNORECASE)
                    cleaned_text = cleaned_text.strip()

            text = cleaned_text
            logger.debug(f"[CHOICES PARSE] Removed markdown code blocks, final text length: {len(text)}")

        # === STRATEGY 1: Try to parse as {"choices": [...]} wrapper first ===
        # This is the format we request in the prompt
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "choices" in parsed:
                choices = parsed["choices"]
                result = _validate_and_return_choices(choices)
                if result:
                    return result
        except json.JSONDecodeError:
            pass

        # === STRATEGY 2: Try with malformed escaping fixes ===
        fixed_text = fix_malformed_json_escaping(text)
        if fixed_text != text:
            try:
                parsed = json.loads(fixed_text)
                if isinstance(parsed, dict) and "choices" in parsed:
                    choices = parsed["choices"]
                    result = _validate_and_return_choices(choices)
                    if result:
                        logger.debug("[CHOICES PARSE] Succeeded after fixing malformed escaping")
                        return result
                elif isinstance(parsed, list):
                    result = _validate_and_return_choices(parsed)
                    if result:
                        logger.debug("[CHOICES PARSE] Succeeded after fixing malformed escaping (array)")
                        return result
            except json.JSONDecodeError:
                pass

        # === STRATEGY 3: Try to find JSON array directly ===
        # First check if we have an incomplete array (starts with [ but doesn't end with ])
        incomplete_match = None
        if text.strip().startswith('[') and not text.strip().endswith(']'):
            # Try to find the opening bracket and extract everything after it
            bracket_pos = text.find('[')
            if bracket_pos != -1:
                incomplete_match = text[bracket_pos:]

        # Use non-greedy match first, then try greedy if that fails
        json_match = re.search(r'\[.*?\]', text, re.DOTALL)
        if not json_match:
            # Try greedy match in case array spans multiple lines
            json_match = re.search(r'\[.*\]', text, re.DOTALL)

        # If we found a complete match, use it
        if json_match:
            json_str = json_match.group(0)

            try:
                choices = json.loads(json_str)
                return _validate_and_return_choices(choices)
            except json.JSONDecodeError as e:
                logger.warning(f"[CHOICES PARSE] JSON decode error: {e}, JSON string: {json_str[:200]}")

                # Try with malformed escaping fixes
                fixed_json_str = fix_malformed_json_escaping(json_str)
                try:
                    choices = json.loads(fixed_json_str)
                    result = _validate_and_return_choices(choices)
                    if result:
                        logger.debug("[CHOICES PARSE] Succeeded after fixing array escaping")
                        return result
                except json.JSONDecodeError:
                    pass

                # Try to fix common JSON issues - remove trailing commas
                json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                try:
                    choices = json.loads(json_str)
                    return _validate_and_return_choices(choices)
                except json.JSONDecodeError as e2:
                    logger.warning(f"[CHOICES PARSE] Still failed after cleanup: {e2}")
                    # Try to fix incomplete JSON
                    fixed_json = fix_incomplete_json_array(json_str)
                    if fixed_json:
                        try:
                            choices = json.loads(fixed_json)
                            return _validate_and_return_choices(choices)
                        except json.JSONDecodeError:
                            pass
        elif incomplete_match:
            # We have an incomplete array, try to fix it
            logger.warning(f"[CHOICES PARSE] Incomplete JSON array detected, attempting to fix. Text preview: {incomplete_match[:200]}")
            fixed_json = fix_incomplete_json_array(incomplete_match)
            if fixed_json:
                try:
                    choices = json.loads(fixed_json)
                    return _validate_and_return_choices(choices)
                except json.JSONDecodeError as e:
                    logger.warning(f"[CHOICES PARSE] Failed to parse fixed incomplete JSON: {e}")

        # === STRATEGY 4: Regex fallback - extract quoted strings directly ===
        logger.debug("[CHOICES PARSE] Trying regex fallback to extract choices")
        regex_choices = extract_choices_with_regex(original_text)
        if regex_choices:
            return regex_choices

        # If we get here, all parsing attempts failed
        # Check if text looks like it was cut off (incomplete JSON)
        if text.strip().startswith('[') and not text.strip().endswith(']'):
            logger.warning(f"[CHOICES PARSE] Incomplete JSON array detected (starts with '[' but doesn't end with ']'). Text may have been truncated. Text preview: {text[:200]}")
        elif text.strip().startswith('{') and not text.strip().endswith('}'):
            logger.warning(f"[CHOICES PARSE] Incomplete JSON object detected. Text may have been truncated. Text preview: {text[:200]}")
        elif '```json' in text.lower() or '```' in text:
            logger.warning(f"[CHOICES PARSE] Markdown code block found but no valid JSON inside. Text preview: {text[:200]}")
        else:
            logger.warning(f"[CHOICES PARSE] No valid JSON found in text. Text preview: {text[:200]}")

        return None
    except (json.JSONDecodeError, ValueError, AttributeError, Exception) as e:
        logger.warning(f"[CHOICES PARSE] Failed to parse choices from JSON: {e}, text preview: {text[:200] if 'text' in locals() and text else 'empty'}")
        return None


def detect_json_array_in_prose(text: str, min_scene_length: int = 200) -> Tuple[str, Optional[List[str]]]:
    """
    Detect JSON array anywhere in prose text.

    Since story prose NEVER contains JSON arrays like ["...", "..."],
    any such pattern is almost certainly choice data that the LLM output
    without proper markers.

    Args:
        text: The full response text
        min_scene_length: Minimum chars before JSON to consider it as choices (not scene content)

    Returns:
        Tuple of (scene_content, parsed_choices) where parsed_choices may be None
    """
    if not text or len(text) < min_scene_length:
        return (text, None)

    # Pattern to find JSON array start - matches both ["..."] and ['...']
    # Look for [ followed by quote (single or double) with optional whitespace
    json_start_pattern = r'\[\s*["\']'

    # Find all potential JSON array starts
    for match in re.finditer(json_start_pattern, text):
        start_pos = match.start()

        # Only consider if there's substantial content before it (likely scene content)
        if start_pos < min_scene_length:
            continue

        # Extract from the [ to end of text
        potential_json = text[start_pos:]

        # Try to find the closing bracket
        # Use a simple bracket counter that handles strings
        bracket_count = 0
        in_string = False
        string_char = None
        escaped = False
        end_pos = None

        for i, char in enumerate(potential_json):
            if escaped:
                escaped = False
                continue

            if char == '\\':
                escaped = True
                continue

            if not in_string:
                if char in '"\'':
                    in_string = True
                    string_char = char
                elif char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_pos = i + 1
                        break
            else:
                if char == string_char:
                    in_string = False
                    string_char = None

        if end_pos is None:
            # No closing bracket found, try to fix incomplete array
            json_str = potential_json
        else:
            json_str = potential_json[:end_pos]

        # Try to parse this as choices
        # First, try to fix single quotes if present
        if "'" in json_str and '"' not in json_str:
            json_str = fix_single_quotes_to_double(json_str)

        parsed = parse_choices_from_json(json_str)
        if parsed and len(parsed) >= 2:
            scene_content = text[:start_pos].strip()
            logger.debug(f"[CHOICES DETECTION] Found JSON array in prose at position {start_pos}")
            return (scene_content, parsed)

    return (text, None)


def extract_choices_from_response_end(full_text: str) -> Tuple[str, Optional[List[str]]]:
    """
    Extract choices from the end of a response.
    Looks for choices in the last ~1500 chars where they typically appear.

    Returns:
        Tuple of (scene_content, parsed_choices) where parsed_choices may be None
    """
    if not full_text:
        return (full_text, None)

    # Only search in the last portion of the response
    search_region = full_text[-1500:] if len(full_text) > 1500 else full_text
    search_start = len(full_text) - len(search_region)

    # Try multiple marker patterns
    marker_patterns = [
        r'###\s*CHOICES\s*###',
        r'##\s*CHOICES\s*##',
        r'#\s*CHOICES\s*#',
        r'\n\s*CHOICES\s*:\s*\n',
        r'\n\s*\*\*CHOICES\*\*\s*\n',
    ]

    for pattern in marker_patterns:
        match = re.search(pattern, search_region, re.IGNORECASE)
        if match:
            # Calculate position in full text
            marker_pos = search_start + match.start()
            scene = full_text[:marker_pos].strip()
            choices_text = full_text[marker_pos + len(match.group()):].strip()
            parsed = parse_choices_from_json(choices_text)
            if parsed:
                logger.debug(f"[CHOICES EXTRACTION] Found marker '{match.group().strip()}' at position {marker_pos}")
                return (scene, parsed)

    # Special case: Handle "CHOICES [...]" format (LLM outputs choices word followed by JSON array)
    choices_word_match = re.search(r'\n\s*CHOICES\s+(\[.+\])\s*$', search_region, re.IGNORECASE | re.DOTALL)
    if choices_word_match:
        marker_pos = search_start + choices_word_match.start()
        scene = full_text[:marker_pos].strip()
        choices_json = choices_word_match.group(1)
        parsed = parse_choices_from_json(choices_json)
        if parsed:
            logger.debug(f"[CHOICES EXTRACTION] Found 'CHOICES [...]' format at position {marker_pos}")
            return (scene, parsed)

    # === IMPROVED FALLBACK: Robust JSON array detection ===
    # Since story prose NEVER contains JSON arrays, any array pattern is likely choices

    # Pattern 1: JSON array with double quotes (handles escaped quotes inside strings)
    # Uses a more permissive pattern that doesn't require array at absolute end
    json_patterns = [
        # Double-quoted array - handles escaped quotes with (?:[^"\\]|\\.)*
        r'\[\s*"(?:[^"\\]|\\.)*"\s*(?:,\s*"(?:[^"\\]|\\.)*"\s*)+\]',
        # Single-quoted array (some LLMs use single quotes)
        r"\[\s*'(?:[^'\\]|\\.)*'\s*(?:,\s*'(?:[^'\\]|\\.)*'\s*)+\]",
    ]

    for pattern in json_patterns:
        json_match = re.search(pattern, search_region, re.DOTALL)
        if json_match:
            json_str = json_match.group()

            # If single-quoted, convert to double quotes
            if json_str.startswith("[") and "'" in json_str and '"' not in json_str:
                json_str = fix_single_quotes_to_double(json_str)

            parsed = parse_choices_from_json(json_str)
            if parsed and len(parsed) >= 2:
                marker_pos = search_start + json_match.start()
                scene = full_text[:marker_pos].strip()
                logger.debug(f"[CHOICES EXTRACTION] Found JSON array at position {marker_pos} (improved pattern)")
                return (scene, parsed)

    # Pattern 2: Use the prose detection as final fallback
    # This handles cases where the array might be malformed or split across regions
    scene, choices = detect_json_array_in_prose(full_text, min_scene_length=200)
    if choices:
        return (scene, choices)

    return (full_text, None)
