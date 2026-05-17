"""
Plot Parser Module

Provides functions to parse and extract plot points from LLM responses.
Handles various formats including JSON, numbered lists, and markdown.
"""

import re
import json
import logging
from typing import List

logger = logging.getLogger(__name__)

# Standard plot point names
PLOT_POINT_NAMES = [
    "Opening Hook", "Inciting Incident", "Rising Action", "Climax", "Resolution"
]

# Fallback plot points when parsing fails
FALLBACK_PLOT_POINTS = [
    "The story begins with an intriguing hook that draws readers in.",
    "A pivotal event changes everything and sets the main conflict in motion.",
    "Challenges and obstacles test the characters' resolve and growth.",
    "The climax brings all conflicts to a head in an intense confrontation.",
    "The resolution ties up loose ends and shows character transformation."
]


def get_plot_point_name(index: int) -> str:
    """Get plot point name by index"""
    return PLOT_POINT_NAMES[min(index, len(PLOT_POINT_NAMES) - 1)]


def clean_plot_point(text: str, plot_point_names: List[str] = None) -> str:
    """Clean a plot point by removing markers and formatting"""
    if plot_point_names is None:
        plot_point_names = PLOT_POINT_NAMES

    clean_text = text.strip()

    # Remove leading numbers and dots (1., 2., etc.)
    clean_text = re.sub(r'^\d+\.\s*', '', clean_text)

    # Remove leading bullets
    clean_text = re.sub(r'^[\-\*\•]\s+', '', clean_text)

    # Remove markdown bold formatting
    plot_point_pattern = "|".join(plot_point_names)
    clean_text = re.sub(r'^\*\*(' + plot_point_pattern + r')\*\*\s*:?\s*', '', clean_text, flags=re.IGNORECASE)

    # Remove plot point names with colons
    clean_text = re.sub(r'^(' + plot_point_pattern + r')\s*:?\s*', '', clean_text, flags=re.IGNORECASE)

    # Remove any remaining leading markers
    clean_text = re.sub(r'^[\d\.\-\*\•\s]*', '', clean_text)

    # Clean up extra whitespace
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    return clean_text


def parse_plot_points_json(response: str) -> List[str]:
    """Parse plot points from JSON response"""
    plot_points = []

    try:
        # Clean response - remove markdown code blocks if present
        response_clean = response.strip()

        # Remove markdown code blocks (```json ... ``` or ``` ... ```)
        if response_clean.startswith("```"):
            # Find the closing ```
            end_idx = response_clean.find("```", 3)
            if end_idx != -1:
                response_clean = response_clean[3:end_idx].strip()
                # Remove "json" if it's ```json
                if response_clean.startswith("json"):
                    response_clean = response_clean[4:].strip()

        logger.debug(f"Cleaned response (first 200 chars): {response_clean[:200]}...")

        # Parse JSON
        try:
            data = json.loads(response_clean)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Response that failed to parse: {response_clean[:500]}")
            # Try to extract JSON from the response if it's embedded in text
            # Look for JSON object with plot_points key
            json_start = response_clean.find('{"plot_points"')
            if json_start == -1:
                json_start = response_clean.find("{'plot_points'")
            if json_start != -1:
                # Find matching closing brace
                brace_count = 0
                json_end = json_start
                for i, char in enumerate(response_clean[json_start:], start=json_start):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break

                if json_end > json_start:
                    json_str = response_clean[json_start:json_end]
                    logger.debug("Found JSON-like structure, attempting to parse...")
                    try:
                        # Replace single quotes with double quotes if needed
                        if "'" in json_str and '"' not in json_str:
                            json_str = json_str.replace("'", '"')
                        data = json.loads(json_str)
                    except json.JSONDecodeError as json_err:
                        logger.error(f"Failed to parse extracted JSON: {json_err}")
                        raise ValueError(f"Failed to parse JSON from response: {e}")
                else:
                    raise ValueError(f"Failed to parse JSON from response: {e}")
            else:
                raise ValueError(f"Failed to parse JSON from response: {e}")

        # Extract plot_points from JSON
        if isinstance(data, dict) and "plot_points" in data:
            plot_points = data["plot_points"]
            if not isinstance(plot_points, list):
                raise ValueError(f"plot_points is not a list, got {type(plot_points)}")

            # Validate and clean each plot point
            cleaned_points = []
            for i, point in enumerate(plot_points):
                if not isinstance(point, str):
                    point = str(point)
                point = point.strip()

                # Remove any plot point name prefixes that might be in the text
                for name in PLOT_POINT_NAMES:
                    # Remove patterns like "Opening Hook:", "Opening Hook -", etc.
                    point = re.sub(rf'^{re.escape(name)}\s*[:-]\s*', '', point, flags=re.IGNORECASE)

                if point and len(point) > 10:  # Minimum length check
                    cleaned_points.append(point)
                    logger.debug(f"Extracted plot point #{len(cleaned_points)}: {point[:100]}...")
                else:
                    logger.debug(f"Rejected plot point #{i+1} (too short or empty): '{point[:50] if point else 'empty'}...'")

            plot_points = cleaned_points

            logger.debug(f"Total plot points extracted from JSON: {len(plot_points)}")
        else:
            raise ValueError(f"JSON does not contain 'plot_points' key. Keys found: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")

    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Response that failed: {response[:500]}")
        raise ValueError(f"Failed to parse plot points from JSON response: {str(e)}")

    # Ensure we have exactly 5 plot points
    if len(plot_points) < 5:
        logger.warning(f"Only {len(plot_points)} plot points extracted from JSON, using fallback for remaining")
        plot_points.extend(FALLBACK_PLOT_POINTS[len(plot_points):])

    for i, point in enumerate(plot_points[:5], 1):
        logger.debug(f"Final plot point {i}. {point[:150]}...")

    return plot_points[:5]


def parse_plot_points(response: str) -> List[str]:
    """Parse plot points from response - handles multiple formats"""
    plot_points = []

    # Plot point names for pattern matching
    plot_point_pattern = "|".join(PLOT_POINT_NAMES)

    # Strategy 4: Line-by-line parsing with continuation
    lines = response.split('\n')
    current_point = ""
    found_any_marker = False

    for line in lines:
        line = line.strip()
        if not line:
            # Empty line - if we have a current point, it might be complete
            if current_point and found_any_marker:
                clean_point = clean_plot_point(current_point, PLOT_POINT_NAMES)
                if clean_point and len(clean_point) > 20:
                    plot_points.append(clean_point)
                    logger.debug(f"Extracted plot point #{len(plot_points)}: {clean_point[:100]}...")
                current_point = ""
                found_any_marker = False
            continue

        # Check if this line starts a new plot point
        is_new_point = False

        # Check for numbered format (1., 2., etc.)
        if re.match(r'^\d+\.\s*', line):
            is_new_point = True
            found_any_marker = True
            logger.debug(f"Found numbered marker: {line[:50]}...")

        # Check for plot point name at start
        elif re.match(r'^(' + plot_point_pattern + r')\s*:?\s*', line, re.IGNORECASE):
            is_new_point = True
            found_any_marker = True
            logger.debug(f"Found named marker: {line[:50]}...")

        # Check for markdown bold
        elif re.search(r'\*\*(' + plot_point_pattern + r')\*\*', line, re.IGNORECASE):
            is_new_point = True
            found_any_marker = True
            logger.debug(f"Found markdown marker: {line[:50]}...")

        # Check for bullet points
        elif re.match(r'^[\-\*\•]\s+', line):
            is_new_point = True
            found_any_marker = True
            logger.debug(f"Found bullet marker: {line[:50]}...")

        if is_new_point:
            # Save previous point if exists
            if current_point:
                clean_point = clean_plot_point(current_point, PLOT_POINT_NAMES)
                if clean_point and len(clean_point) > 20:
                    plot_points.append(clean_point)
                    logger.debug(f"Extracted plot point #{len(plot_points)}: {clean_point[:100]}...")
                else:
                    logger.debug(f"Rejected plot point (too short): '{clean_point[:50] if clean_point else 'empty'}...'")
            current_point = line
        else:
            # Continuation of current point
            if current_point:
                current_point += " " + line
            elif not found_any_marker:
                # No markers found yet, might be plain text format
                # Check if line looks like it could be a plot point
                if len(line) > 20 and not re.match(r'^[A-Z\s]+$', line):  # Not all caps (likely a heading)
                    current_point = line
                    found_any_marker = True

    # Don't forget the last point
    if current_point:
        clean_point = clean_plot_point(current_point, PLOT_POINT_NAMES)
        if clean_point and len(clean_point) > 20:
            plot_points.append(clean_point)
            logger.debug(f"Extracted plot point #{len(plot_points)}: {clean_point[:100]}...")
        else:
            logger.debug(f"Rejected final plot point (too short): '{clean_point[:50] if clean_point else 'empty'}...'")

    # If we didn't find any markers, try to split by common separators
    if len(plot_points) == 0:
        logger.warning("No plot points found with markers, trying alternative parsing...")
        # Try splitting by double newlines or numbered patterns
        sections = re.split(r'\n\s*\n|\d+\.\s*', response)
        for section in sections:
            section = section.strip()
            if section and len(section) > 20:
                # Remove any plot point names from the start
                clean_section = clean_plot_point(section, PLOT_POINT_NAMES)
                if clean_section and len(clean_section) > 20:
                    plot_points.append(clean_section)
                    logger.debug(f"Extracted plot point #{len(plot_points)} (alternative method): {clean_section[:100]}...")

    logger.debug(f"Total plot points extracted: {len(plot_points)}")

    # Ensure we have exactly 5 plot points
    if len(plot_points) < 5:
        logger.warning(f"Only {len(plot_points)} plot points extracted, using fallback for remaining")
        logger.debug(f"Response format analysis: Found markers={found_any_marker}, Response preview: {response[:200]}...")
        plot_points.extend(FALLBACK_PLOT_POINTS[len(plot_points):])

    for i, point in enumerate(plot_points[:5], 1):
        logger.debug(f"Final plot point {i}. {point[:150]}...")

    return plot_points[:5]


def detect_pov(text: str) -> str:
    """
    Detect point of view (1st person vs 3rd person) from text.
    Returns 'first' or 'third'
    """
    if not text:
        return 'third'  # Default to third person

    # Look for first person indicators
    first_person_patterns = [
        r'\bI\b', r'\bme\b', r'\bmy\b', r'\bmyself\b', r'\bmine\b',
        r'\bwe\b', r'\bus\b', r'\bour\b', r'\bourselves\b'
    ]

    # Look for third person indicators
    third_person_patterns = [
        r'\bhe\b', r'\bshe\b', r'\bthey\b', r'\bhim\b', r'\bher\b',
        r'\bhis\b', r'\bhers\b', r'\btheirs\b', r'\bthem\b'
    ]

    text_lower = text.lower()

    first_person_count = sum(len(re.findall(pattern, text_lower)) for pattern in first_person_patterns)
    third_person_count = sum(len(re.findall(pattern, text_lower)) for pattern in third_person_patterns)

    # If first person indicators are significantly more common, return first
    if first_person_count > third_person_count * 1.5:
        return 'first'

    # Default to third person
    return 'third'
