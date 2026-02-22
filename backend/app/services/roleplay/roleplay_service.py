"""
Roleplay Service — Main Orchestrator

Handles creating roleplays, generating AI responses, and managing sessions.
Roleplays are stored as Story records with story_mode=ROLEPLAY.
Turns are stored as Scenes with SceneVariants.
"""

import json
import logging
from typing import AsyncGenerator, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func

from ...models.story import Story, StoryStatus, StoryMode
from ...models.story_branch import StoryBranch
from ...models.chapter import Chapter
from ...models.scene import Scene
from ...models.scene_variant import SceneVariant
from ...models.story_flow import StoryFlow
from ...models.character import StoryCharacter
from ..llm.service import UnifiedLLMService
from .context_builder import RoleplayContextBuilder
from .character_loader import CharacterLoader
from .turn_resolver import resolve_active_characters, resolve_auto_continue_characters

logger = logging.getLogger(__name__)

# Shared LLM service instance
_llm_service = UnifiedLLMService()


class RoleplayService:
    """Orchestrates roleplay creation, generation, and management."""

    # --- Creation ---

    @staticmethod
    async def create_roleplay(
        db: Session,
        user_id: int,
        config: dict,
        user_settings: dict,
    ) -> dict:
        """
        Create a new roleplay session.

        Config should contain:
            title: str
            scenario: str (optional)
            setting: str (optional)
            tone: str (optional)
            content_rating: "sfw" | "nsfw"
            characters: list of {character_id, role?, source_story_id?, source_branch_id?, talkativeness?, is_player?}
            player_mode: "character" | "narrator" | "director"
            roleplay_settings: {turn_mode, response_length, auto_continue, max_auto_turns, narration_style}

        Returns dict with story_id and opening scene data.
        """
        # Build roleplay_settings for story_context
        rp_settings = config.get("roleplay_settings", {})
        rp_settings.setdefault("turn_mode", "natural")
        rp_settings.setdefault("response_length", "concise")
        rp_settings.setdefault("auto_continue", False)
        rp_settings.setdefault("max_auto_turns", 2)
        rp_settings.setdefault("narration_style", "moderate")
        rp_settings["player_mode"] = config.get("player_mode", "character")

        # Build talkativeness map
        char_configs = config.get("characters", [])
        talkativeness_map = {}
        for cc in char_configs:
            # Will be keyed by StoryCharacter.id after creation
            talkativeness_map[str(cc.get("character_id", 0))] = cc.get("talkativeness", 0.5)

        # Create the Story record
        story = Story(
            title=config.get("title", "Untitled Roleplay"),
            description=config.get("scenario", ""),
            owner_id=user_id,
            story_mode=StoryMode.ROLEPLAY,
            status=StoryStatus.ACTIVE,
            genre="roleplay",
            tone=config.get("tone", ""),
            world_setting=config.get("setting", ""),
            scenario=config.get("scenario", ""),
            content_rating=config.get("content_rating", "sfw"),
            story_context={
                "roleplay_settings": rp_settings,
                "character_talkativeness": {},  # Will be updated with StoryCharacter IDs
                "voice_mapping": config.get("voice_mapping", {}),
            },
            creation_step=5,  # Skip creation wizard steps
        )
        db.add(story)
        db.flush()  # Get story.id

        # Create main branch
        branch = StoryBranch(
            story_id=story.id,
            name="main",
            is_main=True,
        )
        db.add(branch)
        db.flush()

        story.current_branch_id = branch.id

        # Create a single chapter for the RP
        chapter = Chapter(
            story_id=story.id,
            branch_id=branch.id,
            chapter_number=1,
            title="Roleplay",
            scenario=config.get("scenario", ""),
        )
        db.add(chapter)
        db.flush()

        # Create StoryCharacters with development stages
        story_characters = await CharacterLoader.create_rp_story_characters(
            db, story.id, branch.id, char_configs
        )

        # Update talkativeness map with actual StoryCharacter IDs
        updated_talkativeness = {}
        for sc, cc in zip(story_characters, char_configs):
            updated_talkativeness[str(sc.id)] = cc.get("talkativeness", 0.5)
            # Also update player_character_id in rp_settings
            if cc.get("is_player", False):
                rp_settings["player_character_id"] = sc.id

        story.story_context["character_talkativeness"] = updated_talkativeness
        story.story_context["roleplay_settings"] = rp_settings

        # Mark story_context as modified for SQLAlchemy
        from sqlalchemy.orm import attributes
        attributes.flag_modified(story, "story_context")

        db.commit()
        db.refresh(story)

        logger.info(
            f"Created roleplay story_id={story.id} with {len(story_characters)} characters"
        )

        return {
            "story_id": story.id,
            "branch_id": branch.id,
            "chapter_id": chapter.id,
            "characters": [
                {
                    "story_character_id": sc.id,
                    "character_id": sc.character_id,
                    "name": sc.character.name,
                    "role": sc.role,
                    "is_player": sc.is_player_character,
                }
                for sc in story_characters
            ],
        }

    # --- Generation ---

    @staticmethod
    async def generate_opening(
        db: Session,
        story_id: int,
        user_id: int,
        user_settings: dict,
    ) -> AsyncGenerator[str, None]:
        """
        Generate the opening scene for a roleplay.
        Yields streaming chunks of the opening content.
        """
        story = db.query(Story).filter(Story.id == story_id, Story.owner_id == user_id).first()
        if not story:
            raise ValueError(f"Roleplay {story_id} not found")

        context = await RoleplayContextBuilder.build_context(db, story, user_settings)
        messages = RoleplayContextBuilder.build_message_prefix(context, user_settings)

        # Build opening task
        ai_characters = [c["name"] for c in context["characters"] if not c["is_player"]]
        player_name = context["player_character"]["name"] if context["player_character"] else "the user"

        task = RoleplayContextBuilder.build_opening_task(
            character_names=ai_characters,
            player_name=player_name,
            scenario=story.scenario or story.description or "Start the roleplay",
            rp_settings=context["rp_settings"],
        )
        messages.append({"role": "user", "content": task})

        # Stream the response
        max_tokens = user_settings.get("generation_preferences", {}).get("max_tokens", 2000)
        async for chunk in _llm_service._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens,
            skip_nsfw_filter=True,  # Already injected by context builder
        ):
            yield chunk

    @staticmethod
    async def generate_response(
        db: Session,
        story_id: int,
        user_id: int,
        user_input: str,
        input_mode: str,
        user_settings: dict,
        active_character_ids: Optional[list[int]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate an AI response to the user's turn.
        Yields streaming chunks.

        Args:
            user_input: What the user typed
            input_mode: "character", "narration", or "direction"
            active_character_ids: Override which characters respond (manual mode)
        """
        story = db.query(Story).filter(Story.id == story_id, Story.owner_id == user_id).first()
        if not story:
            raise ValueError(f"Roleplay {story_id} not found")

        context = await RoleplayContextBuilder.build_context(db, story, user_settings)
        rp_settings = context["rp_settings"]
        player_name = context["player_character"]["name"] if context["player_character"] else "the user"
        turn_mode = rp_settings.get("turn_mode", "natural")

        # Resolve which characters respond
        if active_character_ids:
            # Explicit override (manual mode from frontend)
            active_chars, _ = resolve_active_characters(
                user_message=user_input,
                characters=context["characters"],
                turn_mode="manual",
                manual_selection=active_character_ids,
            )
        else:
            last_idx = rp_settings.get("_last_responder_idx", -1)
            active_chars, new_idx = resolve_active_characters(
                user_message=user_input,
                characters=context["characters"],
                turn_mode=turn_mode,
                last_responder_idx=last_idx,
            )
            # Persist round-robin index
            if turn_mode == "round_robin" and new_idx != last_idx:
                rp_settings["_last_responder_idx"] = new_idx
                story.story_context["roleplay_settings"] = rp_settings
                from sqlalchemy.orm import attributes
                attributes.flag_modified(story, "story_context")
                db.flush()

        active_names = [c["name"] for c in active_chars]
        if not active_names:
            raise ValueError("No active AI characters to respond")

        # Build messages
        messages = RoleplayContextBuilder.build_message_prefix(context, user_settings)

        # Multi-query semantic improvement (only for sessions with enough turns)
        turn_count = (
            db.query(sql_func.count(StoryFlow.id))
            .filter(StoryFlow.story_id == story.id, StoryFlow.is_active == True)
            .scalar()
        ) or 0
        if turn_count > 15:
            await RoleplayContextBuilder.improve_semantic_search(
                context, messages, user_input, user_settings, user_id, db
            )

        task = RoleplayContextBuilder.build_task_message(
            user_input=user_input,
            input_mode=input_mode,
            active_character_names=active_names,
            player_name=player_name,
            rp_settings=rp_settings,
        )
        messages.append({"role": "user", "content": task})

        # Stream the response
        max_tokens = user_settings.get("generation_preferences", {}).get("max_tokens", 2000)
        async for chunk in _llm_service._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens,
            skip_nsfw_filter=True,
        ):
            yield chunk

    @staticmethod
    async def auto_continue(
        db: Session,
        story_id: int,
        user_id: int,
        num_turns: int,
        user_settings: dict,
    ) -> AsyncGenerator[str, None]:
        """
        Generate multiple AI turns without user input (characters talk among themselves).

        Yields SSE-compatible events:
            __AUTO_TURN_START__:N  — signals start of auto turn N
            (content chunks)      — normal text chunks
            __AUTO_TURN_COMPLETE__:N:scene_id:variant_id — signals turn N saved

        Args:
            num_turns: Number of turns to generate (capped by max_auto_turns setting)
        """
        story = db.query(Story).filter(Story.id == story_id, Story.owner_id == user_id).first()
        if not story:
            raise ValueError(f"Roleplay {story_id} not found")

        rp_settings = (story.story_context or {}).get("roleplay_settings", {})
        max_auto = rp_settings.get("max_auto_turns", 3)
        num_turns = min(num_turns, max_auto)
        turn_mode = rp_settings.get("turn_mode", "natural")
        chapter_id = story.chapters[0].id if story.chapters else None

        for turn_num in range(1, num_turns + 1):
            yield f"__AUTO_TURN_START__:{turn_num}"

            # Rebuild context each turn (includes newly added turns)
            context = await RoleplayContextBuilder.build_context(db, story, user_settings)
            player_name = context["player_character"]["name"] if context["player_character"] else "the user"

            # Resolve characters purely by talkativeness
            last_idx = rp_settings.get("_last_responder_idx", -1)
            active_chars, new_idx = resolve_auto_continue_characters(
                characters=context["characters"],
                turn_mode=turn_mode,
                last_responder_idx=last_idx,
            )

            if turn_mode == "round_robin" and new_idx != last_idx:
                rp_settings["_last_responder_idx"] = new_idx
                story.story_context["roleplay_settings"] = rp_settings
                from sqlalchemy.orm import attributes
                attributes.flag_modified(story, "story_context")
                db.flush()

            active_names = [c["name"] for c in active_chars]
            if not active_names:
                break

            # Build prompt
            messages = RoleplayContextBuilder.build_message_prefix(context, user_settings)

            # Multi-query semantic improvement for auto-continue
            # Use last portion of recent turns as intent (no user input in auto-continue)
            ac_turn_count = (
                db.query(sql_func.count(StoryFlow.id))
                .filter(StoryFlow.story_id == story.id, StoryFlow.is_active == True)
                .scalar()
            ) or 0
            if ac_turn_count > 15 and context.get("recent_turns"):
                ac_intent = context["recent_turns"][-500:]
                await RoleplayContextBuilder.improve_semantic_search(
                    context, messages, ac_intent, user_settings, user_id, db
                )

            task = RoleplayContextBuilder.build_auto_continue_task(
                active_character_names=active_names,
                player_name=player_name,
                rp_settings=rp_settings,
            )
            messages.append({"role": "user", "content": task})

            # Stream and collect
            full_content = ""
            max_tokens = user_settings.get("generation_preferences", {}).get("max_tokens", 2000)
            async for chunk in _llm_service._generate_stream_with_messages(
                messages=messages,
                user_id=user_id,
                user_settings=user_settings,
                max_tokens=max_tokens,
                skip_nsfw_filter=True,
            ):
                if chunk.startswith("__THINKING__:"):
                    continue
                full_content += chunk
                yield chunk

            # Save the turn
            scene, variant = RoleplayService.save_ai_turn(
                db, story.id, story.current_branch_id, chapter_id,
                content=full_content,
            )
            db.commit()

            yield f"__AUTO_TURN_COMPLETE__:{turn_num}:{scene.id}:{variant.id}"

    # --- Turn persistence ---

    @staticmethod
    def save_user_turn(
        db: Session,
        story_id: int,
        branch_id: int,
        chapter_id: int,
        content: str,
        generation_method: str = "user_written",
    ) -> tuple:
        """Save the user's turn as a Scene + SceneVariant."""
        return RoleplayService._save_turn(
            db, story_id, branch_id, chapter_id,
            content=content,
            generation_method=generation_method,
        )

    @staticmethod
    def save_ai_turn(
        db: Session,
        story_id: int,
        branch_id: int,
        chapter_id: int,
        content: str,
    ) -> tuple:
        """Save the AI's response as a Scene + SceneVariant."""
        return RoleplayService._save_turn(
            db, story_id, branch_id, chapter_id,
            content=content,
            generation_method="auto",
        )

    @staticmethod
    def _save_turn(
        db: Session,
        story_id: int,
        branch_id: int,
        chapter_id: int,
        content: str,
        generation_method: str,
    ) -> tuple:
        """
        Internal: create a Scene + SceneVariant + StoryFlow for a turn.
        Returns (scene, variant).
        """
        # Get next sequence number
        max_seq = (
            db.query(sql_func.max(Scene.sequence_number))
            .filter(Scene.story_id == story_id)
            .scalar()
        ) or 0
        next_seq = max_seq + 1

        scene = Scene(
            story_id=story_id,
            branch_id=branch_id,
            chapter_id=chapter_id,
            sequence_number=next_seq,
        )
        db.add(scene)
        db.flush()

        variant = SceneVariant(
            scene_id=scene.id,
            variant_number=1,
            is_original=True,
            content=content,
            generation_method=generation_method,
        )
        db.add(variant)
        db.flush()

        flow = StoryFlow(
            story_id=story_id,
            sequence_number=next_seq,
            scene_id=scene.id,
            scene_variant_id=variant.id,
            branch_id=branch_id,
            is_active=True,
        )
        db.add(flow)
        db.flush()

        return scene, variant

    # --- Edit / Delete turns ---

    @staticmethod
    def edit_turn(
        db: Session,
        story: Story,
        scene_id: int,
        new_content: str,
    ) -> dict:
        """Edit a turn's content. Tracks original content on first edit."""
        branch_id = story.current_branch_id

        # Find the StoryFlow entry for this scene on the active branch
        flow = (
            db.query(StoryFlow)
            .filter(
                StoryFlow.story_id == story.id,
                StoryFlow.scene_id == scene_id,
                StoryFlow.branch_id == branch_id,
                StoryFlow.is_active == True,
            )
            .first()
        )
        if not flow:
            return None

        variant = db.query(SceneVariant).filter(
            SceneVariant.id == flow.scene_variant_id
        ).first()
        if not variant:
            return None

        # Store original content on first edit
        if not variant.user_edited and not variant.original_content:
            variant.original_content = variant.content

        variant.content = new_content.strip()
        variant.user_edited = True
        db.commit()

        return {
            "scene_id": scene_id,
            "variant_id": variant.id,
            "content": variant.content,
        }

    @staticmethod
    def delete_turns_from(
        db: Session,
        story: Story,
        sequence_number: int,
    ) -> int:
        """Delete all turns from a given sequence number onwards. Returns count deleted."""
        branch_id = story.current_branch_id

        # Delete StoryFlow entries
        flows_deleted = (
            db.query(StoryFlow)
            .filter(
                StoryFlow.story_id == story.id,
                StoryFlow.branch_id == branch_id,
                StoryFlow.sequence_number >= sequence_number,
            )
            .delete()
        )

        # Delete Scene records (cascades to SceneVariant)
        scenes = (
            db.query(Scene)
            .filter(
                Scene.story_id == story.id,
                Scene.branch_id == branch_id,
                Scene.sequence_number >= sequence_number,
            )
            .all()
        )
        for scene in scenes:
            db.delete(scene)

        db.commit()
        return len(scenes)

    # --- Mid-session character management ---

    @staticmethod
    async def add_character(
        db: Session,
        story: Story,
        config: dict,
    ) -> dict:
        """
        Add a character to an active roleplay mid-session.
        Creates StoryCharacter + inserts a narration turn announcing entry.
        """
        from ...models.character import Character

        character_id = config["character_id"]
        char = db.query(Character).filter(Character.id == character_id).first()
        if not char:
            raise ValueError(f"Character {character_id} not found")

        # Check not already in RP
        existing = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == story.id,
            StoryCharacter.character_id == character_id,
            StoryCharacter.is_active == True,
        ).first()
        if existing:
            raise ValueError(f"{char.name} is already in this roleplay")

        # Check for inactive (previously removed) — reactivate instead
        inactive = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == story.id,
            StoryCharacter.character_id == character_id,
            StoryCharacter.is_active == False,
        ).first()

        if inactive:
            inactive.is_active = True
            sc = inactive
        else:
            # Create new StoryCharacter, optionally loading dev state
            chars = await CharacterLoader.create_rp_story_characters(
                db, story.id, story.current_branch_id, [config]
            )
            sc = chars[0]

        # Update talkativeness map
        ctx = story.story_context or {}
        talk_map = ctx.get("character_talkativeness", {})
        talk_map[str(sc.id)] = config.get("talkativeness", 0.5)
        ctx["character_talkativeness"] = talk_map
        story.story_context = ctx

        from sqlalchemy.orm import attributes
        attributes.flag_modified(story, "story_context")

        # Insert narration turn
        chapter_id = story.chapters[0].id if story.chapters else None
        RoleplayService._save_turn(
            db, story.id, story.current_branch_id, chapter_id,
            content=f"*{char.name} enters the scene.*",
            generation_method="direction",
        )

        db.commit()

        logger.info(f"Added character {char.name} (sc={sc.id}) to RP {story.id}")
        return {
            "message": f"{char.name} added to roleplay",
            "story_character_id": sc.id,
            "character_id": char.id,
            "name": char.name,
        }

    @staticmethod
    async def remove_character(
        db: Session,
        story: Story,
        story_character_id: int,
    ) -> Optional[dict]:
        """
        Remove a character from an active roleplay mid-session.
        Sets is_active=False + inserts a narration turn announcing exit.
        """
        sc = db.query(StoryCharacter).filter(
            StoryCharacter.id == story_character_id,
            StoryCharacter.story_id == story.id,
            StoryCharacter.is_active == True,
        ).first()
        if not sc:
            return None

        # Don't allow removing the player character
        if sc.is_player_character:
            raise ValueError("Cannot remove the player character")

        char_name = sc.character.name if sc.character else "A character"
        sc.is_active = False

        # Insert narration turn
        chapter_id = story.chapters[0].id if story.chapters else None
        RoleplayService._save_turn(
            db, story.id, story.current_branch_id, chapter_id,
            content=f"*{char_name} leaves the scene.*",
            generation_method="direction",
        )

        db.commit()

        logger.info(f"Removed character {char_name} (sc={sc.id}) from RP {story.id}")
        return {
            "message": f"{char_name} removed from roleplay",
            "story_character_id": sc.id,
            "name": char_name,
        }

    # --- Retrieval ---

    @staticmethod
    async def get_roleplay(db: Session, story_id: int, user_id: int) -> dict:
        """
        Get a roleplay with its turn history and character info.
        """
        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == user_id,
            Story.story_mode == StoryMode.ROLEPLAY,
        ).first()
        if not story:
            return None

        branch_id = story.current_branch_id

        # Load characters
        story_characters = (
            db.query(StoryCharacter)
            .filter(StoryCharacter.story_id == story_id)
            .all()
        )

        characters = []
        for sc in story_characters:
            char = sc.character
            characters.append({
                "story_character_id": sc.id,
                "character_id": char.id if char else None,
                "name": char.name if char else "Unknown",
                "role": sc.role,
                "is_player": sc.is_player_character,
                "is_active": sc.is_active,
                "source_story_id": sc.source_story_id,
            })

        # Load turns via StoryFlow
        flows = (
            db.query(StoryFlow)
            .filter(
                StoryFlow.story_id == story_id,
                StoryFlow.branch_id == branch_id,
                StoryFlow.is_active == True,
            )
            .order_by(StoryFlow.sequence_number)
            .all()
        )

        turns = []
        for flow in flows:
            variant = db.query(SceneVariant).filter(
                SceneVariant.id == flow.scene_variant_id
            ).first()
            if variant:
                turns.append({
                    "sequence": flow.sequence_number,
                    "scene_id": flow.scene_id,
                    "variant_id": variant.id,
                    "content": variant.content,
                    "generation_method": variant.generation_method,
                    "created_at": variant.created_at.isoformat() if variant.created_at else None,
                })

        rp_settings = (story.story_context or {}).get("roleplay_settings", {})

        return {
            "story_id": story.id,
            "title": story.title,
            "scenario": story.scenario,
            "setting": story.world_setting,
            "tone": story.tone,
            "content_rating": story.content_rating,
            "status": story.status.value if story.status else "active",
            "branch_id": branch_id,
            "roleplay_settings": rp_settings,
            "characters": characters,
            "turns": turns,
            "turn_count": len(turns),
            "created_at": story.created_at.isoformat() if story.created_at else None,
            "updated_at": story.updated_at.isoformat() if story.updated_at else None,
        }

    @staticmethod
    async def list_roleplays(db: Session, user_id: int) -> list[dict]:
        """List all roleplays for a user."""
        stories = (
            db.query(Story)
            .filter(
                Story.owner_id == user_id,
                Story.story_mode == StoryMode.ROLEPLAY,
            )
            .order_by(Story.updated_at.desc().nullslast(), Story.created_at.desc())
            .all()
        )

        results = []
        for story in stories:
            # Get character names
            scs = db.query(StoryCharacter).filter(StoryCharacter.story_id == story.id).all()
            char_names = [sc.character.name for sc in scs if sc.character]

            # Get turn count
            turn_count = (
                db.query(sql_func.count(StoryFlow.id))
                .filter(
                    StoryFlow.story_id == story.id,
                    StoryFlow.is_active == True,
                )
                .scalar()
            ) or 0

            results.append({
                "story_id": story.id,
                "title": story.title,
                "scenario": story.scenario,
                "tone": story.tone,
                "content_rating": story.content_rating,
                "characters": char_names,
                "turn_count": turn_count,
                "created_at": story.created_at.isoformat() if story.created_at else None,
                "updated_at": story.updated_at.isoformat() if story.updated_at else None,
            })

        return results

    @staticmethod
    async def delete_roleplay(db: Session, story_id: int, user_id: int) -> bool:
        """Delete a roleplay and all associated data."""
        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == user_id,
            Story.story_mode == StoryMode.ROLEPLAY,
        ).first()
        if not story:
            return False

        db.delete(story)
        db.commit()
        return True
