"""
Scene verification utilities for post-processing extracted NPCs/events.

This module provides heuristics to verify which NPCs/events belong to which scenes
by analyzing the actual scene text, without relying on LLM to map results.
"""

import re
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Common dialogue tags
DIALOGUE_TAGS = [
    'said', 'replied', 'asked', 'answered', 'exclaimed', 'whispered', 
    'shouted', 'muttered', 'yelled', 'cried', 'called', 'responded',
    'continued', 'added', 'interrupted', 'stated', 'declared', 'announced'
]

# Common action verbs (non-exhaustive list)
ACTION_VERBS = [
    'walked', 'ran', 'moved', 'grabbed', 'looked', 'turned', 'stepped',
    'jumped', 'reached', 'picked', 'threw', 'pushed', 'pulled', 'opened',
    'closed', 'entered', 'left', 'sat', 'stood', 'fell', 'rose', 'climbed',
    'descended', 'attacked', 'defended', 'struck', 'blocked', 'dodged',
    'fled', 'chased', 'followed', 'led', 'stopped', 'started', 'began',
    'ended', 'finished', 'continued', 'paused', 'waited', 'hurried',
    'rushed', 'sprinted', 'dashed', 'crept', 'sneaked', 'stumbled',
    'tripped', 'slipped', 'caught', 'released', 'held', 'dropped',
    'touched', 'pointed', 'gestured', 'nodded', 'shook', 'waved'
]

# Non-action verbs (to exclude from action detection)
NON_ACTION_VERBS = [
    'is', 'was', 'are', 'were', 'been', 'being', 'has', 'have', 'had',
    'seems', 'seemed', 'appears', 'appeared', 'looks', 'looked', 'sounds',
    'sounded', 'feels', 'felt', 'knows', 'knew', 'thinks', 'thought',
    'believes', 'believed', 'wants', 'wanted', 'needs', 'needed'
]


def find_npc_in_scene(scene_content: str, npc_name: str) -> Dict[str, Any]:
    """
    Analyze scene text to determine NPC presence and characteristics.
    
    Args:
        scene_content: Full scene text
        npc_name: Name of NPC to search for
        
    Returns:
        Dictionary with:
        - mentions: int - Number of times NPC is mentioned
        - has_dialogue: bool - Whether NPC has dialogue
        - has_actions: bool - Whether NPC performs actions
        - context_snippets: List[str] - Snippets where NPC appears
    """
    if not scene_content or not npc_name:
        return {
            'mentions': 0,
            'has_dialogue': False,
            'has_actions': False,
            'context_snippets': []
        }
    
    # Case-insensitive search
    npc_lower = npc_name.lower()
    scene_lower = scene_content.lower()
    
    # Count mentions (simple word boundary matching)
    # Escape special regex characters in NPC name
    npc_escaped = re.escape(npc_name)
    mention_pattern = r'\b' + npc_escaped + r'\b'
    mentions = len(re.findall(mention_pattern, scene_content, re.IGNORECASE))
    
    # Find dialogue
    has_dialogue = _detect_dialogue(scene_content, npc_name)
    
    # Find actions
    has_actions = _detect_actions(scene_content, npc_name)
    
    # Extract context snippets (sentences containing NPC name)
    context_snippets = _extract_context_snippets(scene_content, npc_name, max_snippets=3)
    
    return {
        'mentions': mentions,
        'has_dialogue': has_dialogue,
        'has_actions': has_actions,
        'context_snippets': context_snippets
    }


def _detect_dialogue(scene_content: str, npc_name: str, proximity_words: int = 15) -> bool:
    """
    Detect if NPC has dialogue in the scene.
    
    Checks for:
    1. Quoted text near NPC name
    2. Dialogue tags with NPC name
    """
    npc_escaped = re.escape(npc_name)
    npc_pattern = r'\b' + npc_escaped + r'\b'
    
    # Find all positions where NPC name appears
    npc_positions = []
    for match in re.finditer(npc_pattern, scene_content, re.IGNORECASE):
        npc_positions.append(match.start())
    
    if not npc_positions:
        return False
    
    # Check for quoted text near NPC name
    # Look for quotes within proximity_words words
    quote_pattern = r'"[^"]*"'
    for quote_match in re.finditer(quote_pattern, scene_content):
        quote_start = quote_match.start()
        quote_end = quote_match.end()
        
        # Check if any NPC position is near this quote
        for npc_pos in npc_positions:
            # Count words between NPC and quote
            text_between = scene_content[min(npc_pos, quote_start):max(npc_pos, quote_end)]
            word_count = len(text_between.split())
            
            if word_count <= proximity_words:
                return True
    
    # Check for dialogue tags with NPC name
    # Pattern: "text" said NPC or NPC said "text"
    for tag in DIALOGUE_TAGS:
        # Pattern 1: "text" said NPC
        pattern1 = rf'"[^"]*"\s+{tag}\s+{npc_pattern}'
        if re.search(pattern1, scene_content, re.IGNORECASE):
            return True
        
        # Pattern 2: NPC said "text"
        pattern2 = rf'{npc_pattern}\s+{tag}\s+"[^"]*"'
        if re.search(pattern2, scene_content, re.IGNORECASE):
            return True
        
        # Pattern 3: "text," NPC said
        pattern3 = rf'"[^"]*",\s+{npc_pattern}\s+{tag}'
        if re.search(pattern3, scene_content, re.IGNORECASE):
            return True
    
    return False


def _detect_actions(scene_content: str, npc_name: str) -> bool:
    """
    Detect if NPC performs actions in the scene.
    
    Checks for:
    1. Verb patterns after NPC name
    2. Action verbs in sentences containing NPC name
    """
    npc_escaped = re.escape(npc_name)
    npc_pattern = r'\b' + npc_escaped + r'\b'
    
    # Find sentences containing NPC name
    sentences = re.split(r'[.!?]+', scene_content)
    
    for sentence in sentences:
        if not re.search(npc_pattern, sentence, re.IGNORECASE):
            continue
        
        # Check for action verb patterns
        # Pattern 1: NPC verb (e.g., "John walked")
        for verb in ACTION_VERBS:
            pattern = rf'{npc_pattern}\s+{verb}\b'
            if re.search(pattern, sentence, re.IGNORECASE):
                return True
        
        # Pattern 2: NPC adverb verb (e.g., "John quickly ran")
        for verb in ACTION_VERBS:
            pattern = rf'{npc_pattern}\s+\w+\s+{verb}\b'
            if re.search(pattern, sentence, re.IGNORECASE):
                return True
        
        # Pattern 3: Verb in sentence with NPC (check if verb comes after NPC)
        npc_match = re.search(npc_pattern, sentence, re.IGNORECASE)
        if npc_match:
            npc_pos = npc_match.end()
            sentence_after_npc = sentence[npc_pos:]
            
            # Check for action verbs after NPC
            for verb in ACTION_VERBS:
                verb_pattern = r'\b' + verb + r'\b'
                if re.search(verb_pattern, sentence_after_npc, re.IGNORECASE):
                    return True
    
    return False


def _extract_context_snippets(scene_content: str, npc_name: str, max_snippets: int = 3) -> List[str]:
    """
    Extract context snippets (sentences) containing NPC name.
    """
    npc_escaped = re.escape(npc_name)
    npc_pattern = r'\b' + npc_escaped + r'\b'
    
    # Split into sentences
    sentences = re.split(r'([.!?]+)', scene_content)
    # Recombine sentences with their punctuation
    sentences_combined = []
    for i in range(0, len(sentences) - 1, 2):
        if i + 1 < len(sentences):
            sentences_combined.append(sentences[i] + sentences[i + 1])
        else:
            sentences_combined.append(sentences[i])
    
    snippets = []
    for sentence in sentences_combined:
        if re.search(npc_pattern, sentence, re.IGNORECASE):
            snippet = sentence.strip()
            if snippet:
                snippets.append(snippet)
                if len(snippets) >= max_snippets:
                    break
    
    return snippets


def map_npcs_to_scenes(
    extracted_npcs: List[Dict[str, Any]],
    scenes: List[Tuple[int, str]]  # List of (scene_id, scene_content) tuples
) -> Dict[int, List[Dict[str, Any]]]:
    """
    Map extracted NPCs to their respective scenes by scanning scene text.
    
    Args:
        extracted_npcs: List of NPCs extracted from batch (without scene mapping)
        scenes: List of (scene_id, scene_content) tuples
        
    Returns:
        Dictionary mapping scene_id to list of NPCs that appear in that scene
    """
    scene_npc_map = {scene_id: [] for scene_id, _ in scenes}
    
    for npc in extracted_npcs:
        npc_name = npc.get('name', '').strip()
        if not npc_name:
            continue
        
        # Check each scene for this NPC
        for scene_id, scene_content in scenes:
            npc_info = find_npc_in_scene(scene_content, npc_name)
            
            if npc_info['mentions'] > 0:
                # NPC appears in this scene
                scene_npc = {
                    'name': npc_name,
                    'entity_type': npc.get('entity_type', 'CHARACTER'),  # Preserve entity_type from LLM
                    'mention_count': npc_info['mentions'],
                    'has_dialogue': npc_info['has_dialogue'],
                    'has_actions': npc_info['has_actions'],
                    'has_relationships': npc.get('has_relationships', False),  # Keep from LLM
                    'context_snippets': npc_info['context_snippets'] or npc.get('context_snippets', []),
                    'properties': npc.get('properties', {})
                }
                scene_npc_map[scene_id].append(scene_npc)
    
    return scene_npc_map


def map_events_to_scenes(
    extracted_events: List[Dict[str, Any]],
    scenes: List[Tuple[int, str]]  # List of (scene_id, scene_content) tuples
) -> Dict[int, List[Dict[str, Any]]]:
    """
    Map extracted plot events to their respective scenes by scanning scene text.
    
    Uses keyword matching on event description to find which scene it belongs to.
    
    Args:
        extracted_events: List of events extracted from batch
        scenes: List of (scene_id, scene_content) tuples
        
    Returns:
        Dictionary mapping scene_id to list of events that appear in that scene
    """
    scene_event_map = {scene_id: [] for scene_id, _ in scenes}
    
    for event in extracted_events:
        description = event.get('description', '').strip()
        if not description:
            continue
        
        # Extract keywords from event description (first few words)
        description_words = description.lower().split()[:5]  # First 5 words
        keywords = [w for w in description_words if len(w) > 3]  # Words longer than 3 chars
        
        best_match_score = 0
        best_match_scene = None
        
        # Find scene with most keyword matches
        for scene_id, scene_content in scenes:
            scene_lower = scene_content.lower()
            match_score = sum(1 for keyword in keywords if keyword in scene_lower)
            
            if match_score > best_match_score:
                best_match_score = match_score
                best_match_scene = scene_id
        
        # If we found a match, assign event to that scene
        if best_match_scene and best_match_score > 0:
            scene_event_map[best_match_scene].append(event)
        else:
            # Fallback: assign to first scene if no match (shouldn't happen often)
            if scenes:
                logger.debug(f"Could not map event '{description[:50]}...' to any scene, assigning to first scene")
                scene_event_map[scenes[0][0]].append(event)
    
    return scene_event_map


def map_moments_to_scenes(
    extracted_moments: List[Dict[str, Any]],
    scenes: List[Tuple[int, str]],  # List of (scene_id, scene_content) tuples
    character_name: str
) -> Dict[int, List[Dict[str, Any]]]:
    """
    Map extracted character moments to their respective scenes.
    
    Uses character name and moment description to find which scene it belongs to.
    
    Args:
        extracted_moments: List of moments extracted from batch
        scenes: List of (scene_id, scene_content) tuples
        character_name: Name of character these moments belong to
        
    Returns:
        Dictionary mapping scene_id to list of moments that appear in that scene
    """
    scene_moment_map = {scene_id: [] for scene_id, _ in scenes}
    
    for moment in extracted_moments:
        # Handle both 'description' and 'content' keys (content is used by character moments)
        description = moment.get('description', '').strip() or moment.get('content', '').strip()
        if not description:
            continue
        
        # Extract keywords from moment description
        description_words = description.lower().split()[:5]
        keywords = [w for w in description_words if len(w) > 3]
        
        best_match_score = 0
        best_match_scene = None
        
        # Find scene with character name and most keyword matches
        for scene_id, scene_content in scenes:
            scene_lower = scene_content.lower()
            char_name_lower = character_name.lower()
            
            # Must contain character name
            if char_name_lower not in scene_lower:
                continue
            
            match_score = sum(1 for keyword in keywords if keyword in scene_lower)
            
            if match_score > best_match_score:
                best_match_score = match_score
                best_match_scene = scene_id
        
        # Assign moment to best matching scene
        if best_match_scene and best_match_score > 0:
            scene_moment_map[best_match_scene].append(moment)
        else:
            # Fallback: assign to first scene with character name
            for scene_id, scene_content in scenes:
                if character_name.lower() in scene_content.lower():
                    scene_moment_map[scene_id].append(moment)
                    break
    
    return scene_moment_map

