"""
Contradiction Detection Service

Detects continuity errors between scene extractions:
- location_jump: Character moved without travel scene
- knowledge_leak: Character knows something they shouldn't
- state_regression: State reverted without explanation
"""

import logging
import re
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session

from ..models import CharacterState, Contradiction, Character

logger = logging.getLogger(__name__)

# Common words to strip when comparing locations
_LOCATION_STOPWORDS = frozenset({
    'the', 'a', 'an', 'of', 'in', 'at', 'on', 'to', 'and', 'or',
    'with', 'for', 'by', 'from', 'is', 'are', 'was', 'were',
    'specifically', 'focusing', 'particularly', 'mainly', 'especially',
    'currently', 'now', 'still', 'also', 'just', 'area', 'areas',
    'section', 'part', 'region', 'side', 'end',
})


class ContradictionService:
    """Detects continuity errors between extractions."""

    CONTRADICTION_TYPES = [
        'location_jump',      # Character moved without travel scene
        'knowledge_leak',     # Character knows something they shouldn't
        'state_regression',   # State reverted without explanation
        'timeline_error',     # Event order inconsistency
    ]

    def __init__(self, db: Session):
        self.db = db

    async def check_extraction(
        self,
        story_id: int,
        branch_id: int,
        scene_sequence: int,
        new_states: Dict[str, Any],
        chapter_location: Optional[str] = None
    ) -> List[Contradiction]:
        """
        Check new extraction against previous state for contradictions.

        Args:
            story_id: Story ID
            branch_id: Branch ID
            scene_sequence: Current scene sequence number
            new_states: Newly extracted states dict
            chapter_location: Chapter-level location (e.g. "Saran family home")

        Returns:
            List of detected Contradiction objects (not yet committed)
        """
        contradictions = []

        # Get previous character states
        prev_states = self.db.query(CharacterState).filter(
            CharacterState.story_id == story_id,
            CharacterState.branch_id == branch_id
        ).all()

        # Build lookup by character_id
        prev_by_char_id = {s.character_id: s for s in prev_states}

        # Load existing unresolved contradictions for deduplication
        existing = self.db.query(Contradiction).filter(
            Contradiction.story_id == story_id,
            Contradiction.branch_id == branch_id,
            Contradiction.resolved == False
        ).all()
        existing_keys = {
            (c.contradiction_type, (c.character_name or '').lower(), c.scene_sequence)
            for c in existing
        }

        # Check each character in new extraction
        for char_state in new_states.get('characters', []):
            char_name = char_state.get('name')
            if not char_name:
                continue

            # Find matching previous state
            prev = self._find_previous_state(char_name, prev_by_char_id)
            if not prev:
                continue  # New character, no contradiction possible

            # Check for location jump
            location_contradiction = self._check_location_jump(
                char_name, char_state, prev, scene_sequence, story_id, branch_id,
                chapter_location=chapter_location
            )
            if location_contradiction:
                key = ('location_jump', char_name.lower(), scene_sequence)
                if key not in existing_keys:
                    contradictions.append(location_contradiction)
                    existing_keys.add(key)
                else:
                    logger.debug(f"[CONTRADICTION] Skipping duplicate location_jump for {char_name} at scene {scene_sequence}")

            # Check for state regression (emotional state going backward)
            regression_contradiction = self._check_state_regression(
                char_name, char_state, prev, scene_sequence, story_id, branch_id
            )
            if regression_contradiction:
                key = ('state_regression', char_name.lower(), scene_sequence)
                if key not in existing_keys:
                    contradictions.append(regression_contradiction)
                    existing_keys.add(key)
                else:
                    logger.debug(f"[CONTRADICTION] Skipping duplicate state_regression for {char_name} at scene {scene_sequence}")

        # Auto-resolve stale contradictions superseded by new ones
        if contradictions:
            self._auto_resolve_stale(existing, contradictions, scene_sequence)

        return contradictions

    def _auto_resolve_stale(
        self,
        existing: List[Contradiction],
        new_contradictions: List[Contradiction],
        scene_sequence: int
    ) -> None:
        """Auto-resolve older unresolved contradictions superseded by new ones."""
        from datetime import datetime

        # Build set of (type, char_name_lower) from new contradictions
        new_keys = {
            (c.contradiction_type, (c.character_name or '').lower())
            for c in new_contradictions
        }

        resolved_count = 0
        for old in existing:
            if old.resolved:
                continue
            old_key = (old.contradiction_type, (old.character_name or '').lower())
            if old_key in new_keys and old.scene_sequence < scene_sequence:
                old.resolved = True
                old.resolution_note = f"Superseded by scene {scene_sequence}"
                old.resolved_at = datetime.utcnow()
                resolved_count += 1

        if resolved_count:
            logger.info(f"[CONTRADICTION] Auto-resolved {resolved_count} stale contradictions superseded by scene {scene_sequence}")

    def _find_previous_state(
        self,
        char_name: str,
        prev_by_char_id: Dict[int, CharacterState]
    ) -> Optional[CharacterState]:
        """Find previous character state by name."""
        for char_id, state in prev_by_char_id.items():
            # Get character name from the Character model
            char = self.db.query(Character).filter(Character.id == char_id).first()
            if char and char.name.lower() == char_name.lower():
                return state
        return None

    @staticmethod
    def _location_keywords(text: str) -> Set[str]:
        """Extract significant keywords from a location string."""
        words = re.findall(r'[a-z]+', text.lower())
        return {w for w in words if w not in _LOCATION_STOPWORDS and len(w) > 2}

    # Nouns that identify a physical place — if two locations share one of these
    # plus at least one other keyword, they're likely describing the same place.
    _PLACE_NOUNS = frozenset({
        'home', 'house', 'apartment', 'flat', 'condo', 'mansion', 'cottage', 'cabin',
        'room', 'bedroom', 'bathroom', 'kitchen', 'living', 'dining', 'hallway',
        'office', 'building', 'shop', 'store', 'restaurant', 'cafe', 'bar', 'club',
        'school', 'hospital', 'church', 'temple', 'mosque', 'park', 'garden',
        'street', 'road', 'alley', 'bridge', 'station', 'airport', 'port',
        'hotel', 'motel', 'inn', 'lodge', 'resort', 'palace', 'castle', 'tower',
        'basement', 'attic', 'garage', 'porch', 'balcony', 'terrace', 'rooftop',
        'library', 'gym', 'pool', 'lab', 'studio', 'workshop', 'warehouse',
        'market', 'mall', 'plaza', 'square', 'courtyard', 'lobby', 'foyer',
    })

    @staticmethod
    def _locations_are_similar(loc_a: str, loc_b: str) -> bool:
        """
        Check if two location strings describe the same place.

        Uses three keyword-based checks (any passing = same location):
        1. Containment: one normalized string contains the other
        2. Shared place noun + context: both share a place noun and >= 2 overlapping keywords
        3. Keyword overlap: Jaccard similarity of significant words >= 0.4
        """
        a = loc_a.strip().lower()
        b = loc_b.strip().lower()

        # Exact match
        if a == b:
            return True

        # Containment check (one is a substring of the other)
        if a in b or b in a:
            return True

        # Keyword analysis
        kw_a = ContradictionService._location_keywords(a)
        kw_b = ContradictionService._location_keywords(b)

        if kw_a and kw_b:
            overlap = kw_a & kw_b
            union = kw_a | kw_b

            # Shared place noun + context: if they share a core place noun
            # and at least 2 total overlapping words, they describe the same place
            # e.g. "renovated suburban home undergoing renovation" and
            #      "Saran family home...kitchen...undergoing renovation"
            #   → overlap = {home, renovation, undergoing}, includes "home" (place noun)
            if len(overlap) >= 2 and overlap & ContradictionService._PLACE_NOUNS:
                return True

            # High keyword overlap (>= 3 words shared regardless of place nouns)
            if len(overlap) >= 3:
                return True

            # Jaccard similarity
            jaccard = len(overlap) / len(union) if union else 0
            if jaccard >= 0.4:
                return True

        return False

    # Room-level nouns — locations containing these are rooms within a building
    _ROOM_NOUNS = frozenset({
        'bedroom', 'bathroom', 'kitchen', 'living room', 'sunroom', 'dining room',
        'hallway', 'balcony', 'terrace', 'porch', 'garage', 'basement', 'attic',
        'study', 'office', 'foyer', 'lobby', 'den', 'closet', 'pantry', 'laundry',
        'nursery', 'corridor', 'staircase', 'landing', 'veranda',
    })

    # Building-level nouns — chapter locations containing these indicate a building
    _BUILDING_NOUNS = frozenset({
        'home', 'house', 'apartment', 'flat', 'condo', 'mansion', 'cottage',
        'cabin', 'villa', 'bungalow', 'penthouse', 'townhouse', 'duplex',
        'residence', 'manor', 'estate',
        'hotel', 'motel', 'inn', 'lodge', 'resort', 'palace', 'castle',
        'office', 'building', 'hospital', 'school', 'restaurant', 'cafe',
        'bar', 'club', 'temple', 'church', 'mosque',
    })

    @classmethod
    def _is_room_to_room_move(cls, prev_loc: str, new_loc: str, chapter_location: Optional[str]) -> bool:
        """
        Check if a location change is just moving between rooms in the same building.

        Suppresses false-positive location jumps for e.g. "sunroom" → "living room"
        when the chapter location is "Saran family home".
        """
        if not chapter_location:
            return False

        prev_lower = prev_loc.lower()
        new_lower = new_loc.lower()
        chapter_lower = chapter_location.lower()

        # Check if both locations contain room-level nouns
        prev_is_room = any(room in prev_lower for room in cls._ROOM_NOUNS)
        new_is_room = any(room in new_lower for room in cls._ROOM_NOUNS)

        if prev_is_room and new_is_room:
            # Check if chapter location is a building
            chapter_is_building = any(bldg in chapter_lower for bldg in cls._BUILDING_NOUNS)
            if chapter_is_building:
                return True

        # Also suppress if both locations share significant keywords with the chapter location
        chapter_kw = cls._location_keywords(chapter_lower)
        if len(chapter_kw) >= 1:
            prev_kw = cls._location_keywords(prev_lower)
            new_kw = cls._location_keywords(new_lower)
            prev_shared = prev_kw & chapter_kw
            new_shared = new_kw & chapter_kw
            if prev_shared and new_shared:
                return True

        return False

    def _check_location_jump(
        self,
        char_name: str,
        new_state: Dict[str, Any],
        prev_state: CharacterState,
        scene_sequence: int,
        story_id: int,
        branch_id: int,
        chapter_location: Optional[str] = None
    ) -> Optional[Contradiction]:
        """Check if character moved locations without travel."""
        new_location = new_state.get('location', '').strip()
        prev_location = (prev_state.current_location or '').strip()

        # Skip if either location is empty or unknown
        if not new_location or not prev_location:
            return None
        if new_location.lower() in ('unknown', 'null', 'none', ''):
            return None
        if prev_location.lower() in ('unknown', 'null', 'none', ''):
            return None

        # Use fuzzy matching to avoid false positives from rewording
        if self._locations_are_similar(new_location, prev_location):
            return None

        # Suppress room-to-room moves within the same building
        if self._is_room_to_room_move(prev_location, new_location, chapter_location):
            logger.debug(f"[CONTRADICTION] Suppressed room-to-room move for {char_name}: "
                        f'"{prev_location}" → "{new_location}" (chapter: {chapter_location})')
            return None

        # Genuinely different locations — flag as potential jump
        return Contradiction(
            story_id=story_id,
            branch_id=branch_id,
            scene_sequence=scene_sequence,
            contradiction_type='location_jump',
            character_name=char_name,
            previous_value=prev_state.current_location,
            current_value=new_state.get('location'),
            severity='info'  # Info level since travel might be implied
        )

    def _check_state_regression(
        self,
        char_name: str,
        new_state: Dict[str, Any],
        prev_state: CharacterState,
        scene_sequence: int,
        story_id: int,
        branch_id: int
    ) -> Optional[Contradiction]:
        """Check if character's state regressed unexpectedly."""
        # Compare emotional states - check for contradictory emotions
        new_emotion = (new_state.get('emotional_state', '') or '').strip().lower()
        prev_emotion = (prev_state.emotional_state or '').strip().lower()

        if not new_emotion or not prev_emotion:
            return None

        # Define emotion opposites that would indicate regression
        emotion_opposites = {
            'happy': ['sad', 'depressed', 'miserable'],
            'calm': ['angry', 'furious', 'enraged'],
            'confident': ['anxious', 'nervous', 'scared'],
            'hopeful': ['hopeless', 'despairing'],
            'trusting': ['suspicious', 'distrustful'],
        }

        # Check for sudden emotional flip without explanation
        for positive, negatives in emotion_opposites.items():
            # If prev was positive and new is opposite (or vice versa)
            if positive in prev_emotion and any(neg in new_emotion for neg in negatives):
                return Contradiction(
                    story_id=story_id,
                    branch_id=branch_id,
                    scene_sequence=scene_sequence,
                    contradiction_type='state_regression',
                    character_name=char_name,
                    previous_value=prev_state.emotional_state,
                    current_value=new_state.get('emotional_state'),
                    severity='info'  # Info since emotion changes can be valid
                )

        return None

    def get_unresolved(self, story_id: int, branch_id: Optional[int] = None) -> List[Contradiction]:
        """Get all unresolved contradictions for a story."""
        query = self.db.query(Contradiction).filter(
            Contradiction.story_id == story_id,
            Contradiction.resolved == False
        )
        if branch_id:
            query = query.filter(Contradiction.branch_id == branch_id)

        return query.order_by(Contradiction.detected_at.desc()).all()

    def resolve(self, contradiction_id: int, note: str) -> Optional[Contradiction]:
        """Mark a contradiction as resolved with an explanation."""
        from datetime import datetime

        contradiction = self.db.query(Contradiction).filter(
            Contradiction.id == contradiction_id
        ).first()

        if contradiction:
            contradiction.resolved = True
            contradiction.resolution_note = note
            contradiction.resolved_at = datetime.utcnow()
            self.db.commit()

        return contradiction
