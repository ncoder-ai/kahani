"""
Character Loader for Roleplay

Loads character development state from a specific story point
to initialize roleplay characters with their accumulated growth.
"""

import logging
from typing import Optional
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ...models.character import Character, StoryCharacter
from ...models.chronicle import CharacterChronicle
from ...models.entity_state import CharacterState
from ...models.relationship import RelationshipSummary

logger = logging.getLogger(__name__)


class CharacterLoader:
    """Loads character development snapshots for roleplay initialization."""

    @staticmethod
    async def load_character_at_story(
        db: Session,
        character_id: int,
        source_story_id: int,
        source_branch_id: Optional[int] = None,
    ) -> dict:
        """
        Load a character's full development state as of a specific story.

        Returns a dict with chronicle entries, entity state, relationships,
        and voice style that can be used to initialize an RP StoryCharacter.
        """
        character = db.query(Character).filter(Character.id == character_id).first()
        if not character:
            return {}

        # Resolve branch: use provided or fall back to story's current branch
        from ...models.story import Story
        source_story = db.query(Story).filter(Story.id == source_story_id).first()
        if not source_story:
            return {}

        branch_id = source_branch_id or source_story.current_branch_id

        # Load source StoryCharacter for voice style override and role
        source_sc = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == source_story_id,
            StoryCharacter.character_id == character_id,
            or_(
                StoryCharacter.branch_id == branch_id,
                StoryCharacter.branch_id.is_(None),
            ),
        ).first()

        # Chronicle entries — ordered character development milestones
        chronicle_entries = db.query(CharacterChronicle).filter(
            CharacterChronicle.character_id == character_id,
            CharacterChronicle.story_id == source_story_id,
            or_(
                CharacterChronicle.branch_id == branch_id,
                CharacterChronicle.branch_id.is_(None),
            ),
        ).order_by(CharacterChronicle.sequence_order).all()

        # Latest character state from entity extraction
        char_state = db.query(CharacterState).filter(
            CharacterState.character_id == character_id,
            CharacterState.story_id == source_story_id,
            or_(
                CharacterState.branch_id == branch_id,
                CharacterState.branch_id.is_(None),
            ),
        ).order_by(CharacterState.last_updated_scene.desc()).first()

        # Relationship summaries involving this character
        char_name = character.name
        relationships = db.query(RelationshipSummary).filter(
            RelationshipSummary.story_id == source_story_id,
            or_(
                RelationshipSummary.branch_id == branch_id,
                RelationshipSummary.branch_id.is_(None),
            ),
            or_(
                RelationshipSummary.character_a == char_name,
                RelationshipSummary.character_b == char_name,
            ),
        ).all()

        # Build development snapshot
        development_entries = []
        for entry in chronicle_entries:
            development_entries.append({
                "entry_type": entry.entry_type.value if hasattr(entry.entry_type, 'value') else entry.entry_type,
                "description": entry.description,
                "is_defining": entry.is_defining,
            })

        relationship_data = {}
        for rel in relationships:
            other_char = rel.character_b if rel.character_a == char_name else rel.character_a
            relationship_data[other_char] = {
                "type": rel.current_type,
                "strength": rel.current_strength,
                "trajectory": rel.trajectory,
                "arc_summary": rel.arc_summary,
                "total_interactions": rel.total_interactions,
            }

        state_data = {}
        if char_state:
            state_data = {
                "current_location": char_state.current_location,
                "emotional_state": char_state.emotional_state,
                "current_goal": char_state.current_goal,
                "appearance": char_state.appearance,
                "knowledge": char_state.knowledge or [],
                "possessions": char_state.possessions or [],
            }

        return {
            "character_id": character_id,
            "character_name": character.name,
            "source_story_id": source_story_id,
            "source_story_title": source_story.title,
            "source_branch_id": branch_id,
            "development_entries": development_entries,
            "relationships": relationship_data,
            "state": state_data,
            "voice_style_override": source_sc.voice_style_override if source_sc else None,
            "role": source_sc.role if source_sc else None,
        }

    @staticmethod
    async def create_rp_story_characters(
        db: Session,
        story_id: int,
        branch_id: Optional[int],
        character_configs: list[dict],
    ) -> list[StoryCharacter]:
        """
        Create StoryCharacter records for a roleplay, optionally loading
        development state from source stories.

        Each config dict should have:
            character_id: int (required)
            role: str (optional)
            source_story_id: int (optional — load development from this story)
            source_branch_id: int (optional)
            talkativeness: float (optional, 0.0-1.0)
            is_player: bool (optional)
        """
        story_characters = []

        for config in character_configs:
            character_id = config["character_id"]
            source_story_id = config.get("source_story_id")
            source_branch_id = config.get("source_branch_id")
            is_player = config.get("is_player", False)

            # Load development state if source story specified
            dev_snapshot = {}
            if source_story_id:
                dev_snapshot = await CharacterLoader.load_character_at_story(
                    db, character_id, source_story_id, source_branch_id
                )

            sc = StoryCharacter(
                story_id=story_id,
                branch_id=branch_id,
                character_id=character_id,
                role=config.get("role") or dev_snapshot.get("role", "participant"),
                source_story_id=source_story_id,
                source_branch_id=source_branch_id,
                is_player_character=is_player,
                voice_style_override=dev_snapshot.get("voice_style_override"),
                character_development=dev_snapshot.get("development_entries", []),
                relationships=dev_snapshot.get("relationships", {}),
                current_emotional_state=dev_snapshot.get("state", {}).get("emotional_state"),
                current_goals=dev_snapshot.get("state", {}).get("current_goal"),
                current_location=dev_snapshot.get("state", {}).get("current_location"),
                is_active=True,
            )
            db.add(sc)
            story_characters.append(sc)

        db.flush()  # Populate IDs

        logger.info(
            f"Created {len(story_characters)} RP story characters for story {story_id}"
        )
        return story_characters

    @staticmethod
    async def get_character_stories(
        db: Session,
        character_id: int,
        user_id: int,
    ) -> list[dict]:
        """
        Get all stories where a character appears, for the development stage picker.
        Returns [{story_id, title, timeline_order}] ordered by timeline.
        """
        from ...models.story import Story, StoryMode

        results = (
            db.query(Story.id, Story.title, Story.timeline_order, Story.created_at)
            .join(StoryCharacter, StoryCharacter.story_id == Story.id)
            .filter(
                StoryCharacter.character_id == character_id,
                Story.owner_id == user_id,
                Story.story_mode != StoryMode.ROLEPLAY,  # Exclude other RPs
            )
            .distinct()
            .order_by(Story.timeline_order.asc().nullslast(), Story.created_at.asc())
            .all()
        )

        return [
            {"story_id": r.id, "title": r.title, "timeline_order": r.timeline_order}
            for r in results
        ]
