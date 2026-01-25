"""
Contradiction Detection Service

Detects continuity errors between scene extractions:
- location_jump: Character moved without travel scene
- knowledge_leak: Character knows something they shouldn't
- state_regression: State reverted without explanation
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from ..models import CharacterState, Contradiction, Character

logger = logging.getLogger(__name__)


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
        new_states: Dict[str, Any]
    ) -> List[Contradiction]:
        """
        Check new extraction against previous state for contradictions.

        Args:
            story_id: Story ID
            branch_id: Branch ID
            scene_sequence: Current scene sequence number
            new_states: Newly extracted states dict

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
                char_name, char_state, prev, scene_sequence, story_id, branch_id
            )
            if location_contradiction:
                contradictions.append(location_contradiction)

            # Check for state regression (emotional state going backward)
            regression_contradiction = self._check_state_regression(
                char_name, char_state, prev, scene_sequence, story_id, branch_id
            )
            if regression_contradiction:
                contradictions.append(regression_contradiction)

        return contradictions

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

    def _check_location_jump(
        self,
        char_name: str,
        new_state: Dict[str, Any],
        prev_state: CharacterState,
        scene_sequence: int,
        story_id: int,
        branch_id: int
    ) -> Optional[Contradiction]:
        """Check if character moved locations without travel."""
        new_location = new_state.get('location', '').strip().lower()
        prev_location = (prev_state.current_location or '').strip().lower()

        # Skip if either location is empty or unknown
        if not new_location or not prev_location:
            return None
        if new_location in ('unknown', 'null', 'none', ''):
            return None
        if prev_location in ('unknown', 'null', 'none', ''):
            return None

        # Check if locations are different
        if new_location != prev_location:
            # This is a potential location jump
            # In a more sophisticated version, we could check if the scene
            # content mentions travel/movement
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

        return None

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
