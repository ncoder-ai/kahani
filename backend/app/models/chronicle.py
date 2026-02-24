from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum as SQLEnum, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from ..database import Base
from .branch_aware import branch_clone_config, embedding_id_handler
import enum


class ChronicleEntryType(str, enum.Enum):
    PERSONALITY_SHIFT = "personality_shift"
    KNOWLEDGE_GAINED = "knowledge_gained"
    SECRET = "secret"
    RELATIONSHIP_CHANGE = "relationship_change"
    TRAUMA = "trauma"
    PHYSICAL_CHANGE = "physical_change"
    SKILL_GAINED = "skill_gained"
    GOAL_CHANGE = "goal_change"
    OTHER = "other"


def _chronicle_filter(query, fork_seq, story_id, branch_id):
    """Filter chronicle entries up to the fork point."""
    return query.filter(CharacterChronicle.sequence_order <= fork_seq)


@branch_clone_config(
    priority=72,
    depends_on=['scenes'],
    fk_remappings={'scene_id': 'scene_id_map'},
    special_handlers={'embedding_id': embedding_id_handler},
    filter_func=_chronicle_filter,
)
class CharacterChronicle(Base):
    __tablename__ = "character_chronicles"

    id = Column(Integer, primary_key=True, index=True)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    sequence_order = Column(Integer, nullable=False)

    entry_type = Column(
        SQLEnum(ChronicleEntryType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    description = Column(Text, nullable=False)
    is_defining = Column(Boolean, default=False)

    embedding_id = Column(String(200), nullable=True, index=True)
    embedding = Column(Vector(768), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    world = relationship("World")
    character = relationship("Character")
    story = relationship("Story", back_populates="character_chronicles")

    def __repr__(self):
        return f"<CharacterChronicle(id={self.id}, character_id={self.character_id}, entry_type={self.entry_type})>"


def _lorebook_filter(query, fork_seq, story_id, branch_id):
    """Filter lorebook entries up to the fork point."""
    return query.filter(LocationLorebook.sequence_order <= fork_seq)


@branch_clone_config(
    priority=73,
    depends_on=['scenes'],
    fk_remappings={'scene_id': 'scene_id_map'},
    special_handlers={'embedding_id': embedding_id_handler},
    filter_func=_lorebook_filter,
)
class LocationLorebook(Base):
    __tablename__ = "location_lorebooks"

    id = Column(Integer, primary_key=True, index=True)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    sequence_order = Column(Integer, nullable=False)

    location_name = Column(String(200), nullable=False, index=True)
    event_description = Column(Text, nullable=False)

    embedding_id = Column(String(200), nullable=True, index=True)
    embedding = Column(Vector(768), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    world = relationship("World")
    story = relationship("Story", back_populates="location_lorebooks")

    def __repr__(self):
        return f"<LocationLorebook(id={self.id}, location='{self.location_name}')>"


class CharacterSnapshot(Base):
    __tablename__ = "character_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id"), nullable=True, index=True)
    snapshot_text = Column(Text, nullable=False)
    chronicle_entry_count = Column(Integer, nullable=False, default=0)
    timeline_order = Column(Integer, nullable=True)
    up_to_story_id = Column(Integer, ForeignKey("stories.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('world_id', 'character_id', 'branch_id', name='idx_snapshot_world_character_branch'),
    )

    # Relationships
    world = relationship("World")
    character = relationship("Character")
    branch = relationship("StoryBranch")
    up_to_story = relationship("Story")

    def __repr__(self):
        return f"<CharacterSnapshot(id={self.id}, character_id={self.character_id}, world_id={self.world_id})>"
