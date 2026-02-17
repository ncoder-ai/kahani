# Branch-Aware Models Developer Guide

This guide explains how to make new models branch-aware so they are automatically cloned when a story branch is forked.

## Quick Start

When creating a new model that has a `branch_id` column, add the `@branch_clone_config` decorator:

```python
from .branch_aware import branch_clone_config

@branch_clone_config(
    priority=50,  # Clone order (lower = earlier)
)
class MyNewModel(Base):
    __tablename__ = "my_new_models"

    id = Column(Integer, primary_key=True)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)
    # ... other columns
```

That's it! The model will now be automatically cloned when branches are forked.

## Why This Matters

Previously, adding a branch-aware model required manually updating `branch_service.py` with ~50 lines of cloning code. If developers forgot this step, forked branches would have corrupted/missing data.

With the registry system:
1. Add the decorator to your model
2. Branch cloning "just works"
3. Startup validation catches missing registrations

## Decorator Options

### Basic Options

```python
@branch_clone_config(
    priority=50,              # Clone order (required for dependencies)
    depends_on=['chapters'],  # Tables that must be cloned first
    clone_all=False,          # True = clone all records, False = apply filter
)
```

### Foreign Key Remapping

When your model has FKs to other branch-aware tables:

```python
@branch_clone_config(
    priority=70,
    depends_on=['scenes', 'chapters'],
    fk_remappings={
        'scene_id': 'scene_id_map',      # Remap scene_id using scene's ID mapping
        'chapter_id': 'chapter_id_map',  # Remap chapter_id using chapter's ID mapping
    },
)
class MyModel(Base):
    scene_id = Column(Integer, ForeignKey("scenes.id"))
    chapter_id = Column(Integer, ForeignKey("chapters.id"))
```

Available mapping keys:
- `chapter_id_map`
- `scene_id_map`
- `scene_variant_id_map`
- `scene_choice_id_map`
- `story_character_id_map`

### Creating ID Mappings

If other models need to remap FKs to your model:

```python
@branch_clone_config(
    priority=30,
    creates_mapping='my_model_id_map',  # Other models can use this
)
class MyModel(Base):
    ...
```

### Filtering by Fork Point

Most models should only clone records up to the fork point:

```python
def _my_model_filter(query, fork_seq, story_id, branch_id):
    """Filter records up to the fork point."""
    return query.filter(MyModel.sequence_number <= fork_seq)

@branch_clone_config(
    priority=50,
    filter_func=_my_model_filter,
)
class MyModel(Base):
    sequence_number = Column(Integer)  # Scene sequence this relates to
```

Common filter patterns:
- `sequence_number <= fork_seq` - for scene-ordered data
- `last_updated_scene <= fork_seq` - for entity states
- `first_occurrence_scene <= fork_seq` - for first-appearance data
- `end_scene_sequence <= fork_seq` - for batch data

### Self-Referential Foreign Keys

For models that reference themselves (like Scene.parent_scene_id):

```python
@branch_clone_config(
    priority=30,
    creates_mapping='scene_id_map',
    self_ref_fk='parent_scene_id',  # Will be remapped using scene_id_map
)
class Scene(Base):
    parent_scene_id = Column(Integer, ForeignKey("scenes.id"))
```

### Deferred Foreign Keys

For FKs that might point to records not yet cloned (circular references):

```python
@branch_clone_config(
    priority=32,
    creates_mapping='scene_choice_id_map',
    deferred_fk_remappings={
        'leads_to_scene_id': 'scene_id_map',  # Updated after all cloning
    },
)
class SceneChoice(Base):
    leads_to_scene_id = Column(Integer, ForeignKey("scenes.id"))
```

### Nested Models

For models that should be cloned within their parent's loop (e.g., SceneVariant within Scene):

```python
# Parent model
@branch_clone_config(
    priority=30,
    nested_models=['scene_variants', 'scene_choices'],  # Clone these within Scene loop
)
class Scene(Base):
    ...

# Nested model
@branch_clone_config(
    priority=31,
    parent_fk_field='scene_id',  # FK to parent
    has_story_id=False,          # No story_id column
    has_branch_id=False,         # No branch_id column
)
class SceneVariant(Base):
    scene_id = Column(Integer, ForeignKey("scenes.id"))
```

### Special Field Transformations

For fields that need custom handling during cloning:

```python
from .branch_aware import branch_clone_config, embedding_id_handler

@branch_clone_config(
    priority=70,
    special_handlers={
        'embedding_id': embedding_id_handler,  # Appends "_branch_{new_branch_id}"
    },
)
class CharacterMemory(Base):
    embedding_id = Column(String(200), unique=True)  # Must be unique per branch
```

### Clone Transform

For complex transformations that need access to fork_sequence:

```python
def _my_transform(new_data, fork_seq, new_branch_id):
    """Transform data during cloning."""
    if new_data.get('last_scene') and new_data['last_scene'] > fork_seq:
        new_data['last_scene'] = fork_seq  # Clamp to fork point
    return new_data

@branch_clone_config(
    priority=60,
    clone_transform=_my_transform,
)
class MyModel(Base):
    last_scene = Column(Integer)
```

### Resetting Fields

For fields that should be reset in the new branch:

```python
@branch_clone_config(
    priority=32,
    reset_fields={'times_selected': 0},  # Reset counter for new branch
)
class SceneChoice(Base):
    times_selected = Column(Integer, default=0)
```

### Models Without story_id/branch_id

For models linked only via FK to another table (like ChapterSummaryBatch):

```python
@branch_clone_config(
    priority=80,
    depends_on=['chapters'],
    iterate_via_mapping='chapter_id_map',  # Iterate through chapter mapping
    iterate_fk_field='chapter_id',         # FK field to filter/update
    has_story_id=False,
    has_branch_id=False,
)
class ChapterSummaryBatch(Base):
    chapter_id = Column(Integer, ForeignKey("chapters.id"))
```

## Priority Guidelines

| Priority Range | Use For |
|----------------|---------|
| 10-19 | Foundation tables (Chapter) |
| 20-29 | Character tables (StoryCharacter) |
| 30-39 | Scene tables and nested (Scene, SceneVariant, SceneChoice) |
| 40-49 | Flow tables (StoryFlow) |
| 50-59 | Entity states |
| 60-69 | NPC tracking |
| 70-79 | Semantic memory (embeddings, memories, events) |
| 80-89 | Summary/progress batches |
| 85+ | Interaction tracking |

## Branch Deletion

Branch deletion is handled automatically via CASCADE. Ensure your model has:
```python
branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), ...)
```

## Testing Your Model

After adding a branch-aware model, run the test script:

```bash
cd backend
python scripts/test_branch_cloning.py
```

The registry validation will show if your model is registered:
```
Validating registry...
All branch_id tables are registered!
```

## Validation at Startup

To catch missing registrations, add to your app startup:

```python
from app.models import BranchCloneRegistry

unregistered = BranchCloneRegistry.validate()
if unregistered:
    raise RuntimeError(f"Unregistered branch-aware tables: {unregistered}")
```

## Common Mistakes

1. **Forgetting the decorator** - Use `BranchCloneRegistry.validate()` to catch this
2. **Wrong priority** - If your model depends on another, your priority must be higher
3. **Missing depends_on** - If you use `fk_remappings`, add the source table to `depends_on`
4. **Forgetting ondelete="CASCADE"** - Required for branch deletion to work

## Example: Adding a New Feature

Let's say you're adding a "StoryNote" feature for user notes on scenes:

```python
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from ..database import Base
from .branch_aware import branch_clone_config


def _story_note_filter(query, fork_seq, story_id, branch_id):
    """Filter notes for scenes up to the fork point."""
    return query.filter(StoryNote.scene_sequence <= fork_seq)


@branch_clone_config(
    priority=75,
    depends_on=['scenes'],
    fk_remappings={'scene_id': 'scene_id_map'},
    filter_func=_story_note_filter,
)
class StoryNote(Base):
    __tablename__ = "story_notes"

    id = Column(Integer, primary_key=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    scene_sequence = Column(Integer, nullable=False)  # For filtering

    content = Column(Text, nullable=False)
```

That's all you need! The model will now:
- Be cloned when branches are forked
- Only clone notes for scenes up to the fork point
- Have scene_id remapped to the new scene
- Be deleted when the branch is deleted (CASCADE)
