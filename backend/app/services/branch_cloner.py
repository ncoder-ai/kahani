"""
Generic Branch Cloning Service

Uses the BranchCloneRegistry to automatically clone all branch-aware data
when forking a story branch. This eliminates manual maintenance of cloning
code in branch_service.py.
"""

from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import inspect, and_
import logging

from ..models.branch_aware import (
    BranchCloneRegistry,
    BranchCloneConfig,
    STANDARD_SKIP_FIELDS,
)

logger = logging.getLogger(__name__)


class BranchCloner:
    """
    Handles automatic cloning of all branch-aware data.

    Uses the registry to determine what to clone, in what order,
    and how to remap foreign keys.
    """

    def __init__(
        self,
        db: Session,
        story_id: int,
        source_branch_id: int,
        new_branch_id: int,
        fork_sequence: int
    ):
        self.db = db
        self.story_id = story_id
        self.source_branch_id = source_branch_id
        self.new_branch_id = new_branch_id
        self.fork_sequence = fork_sequence

        # ID mappings created during cloning
        # Key: mapping_key (e.g., 'scene_id_map')
        # Value: Dict[old_id, new_id]
        self.id_maps: Dict[str, Dict[int, int]] = {}

        # Statistics: table_name -> count of cloned records
        self.stats: Dict[str, int] = {}

        # Deferred FK updates to apply after all cloning
        self.deferred_updates: List[Dict[str, Any]] = []

    def clone_all(self) -> Dict[str, int]:
        """
        Clone all registered branch-aware tables in dependency order.

        Returns:
            Dict mapping table names to number of records cloned.
        """
        # Get ordered list of tables to clone (respecting dependencies)
        clone_order = BranchCloneRegistry.get_clone_order()

        logger.info(f"Starting branch clone: story={self.story_id}, "
                   f"source_branch={self.source_branch_id}, "
                   f"new_branch={self.new_branch_id}, "
                   f"fork_sequence={self.fork_sequence}")
        logger.debug(f"Clone order: {clone_order}")

        for table_name in clone_order:
            config = BranchCloneRegistry.get(table_name)
            if not config:
                continue

            # Skip nested models (they're cloned by their parent)
            if config.parent_fk_field:
                continue

            try:
                self._clone_table(config)
            except Exception as e:
                logger.error(f"Error cloning table {table_name}: {e}")
                raise

        # Apply deferred FK updates after all records are cloned
        self._apply_deferred_updates()

        logger.info(f"Branch clone complete. Stats: {self.stats}")
        return self.stats

    def _clone_table(self, config: BranchCloneConfig) -> None:
        """Clone a single table based on its configuration."""
        model_class = config.model_class
        table_name = config.table_name

        # Handle models that iterate via a mapping (no story_id/branch_id)
        if config.iterate_via_mapping and config.iterate_fk_field:
            self._clone_via_mapping(config)
            return

        # Build base query
        if config.has_story_id and config.has_branch_id:
            query = self.db.query(model_class).filter(
                and_(
                    model_class.story_id == self.story_id,
                    model_class.branch_id == self.source_branch_id
                )
            )
        elif config.has_branch_id:
            query = self.db.query(model_class).filter(
                model_class.branch_id == self.source_branch_id
            )
        else:
            logger.warning(f"Table {table_name} has no story_id or branch_id, skipping")
            return

        # Apply custom filter if defined (unless clone_all is True)
        if config.filter_func and not config.clone_all:
            query = config.filter_func(
                query, self.fork_sequence, self.story_id, self.source_branch_id
            )

        # Initialize ID mapping if this table creates one
        if config.creates_mapping:
            self.id_maps[config.creates_mapping] = {}

        records_to_clone = query.all()
        logger.info(f"[CLONE] {table_name}: Found {len(records_to_clone)} records to clone from branch {self.source_branch_id}")

        count = 0
        for old_record in records_to_clone:
            new_record = self._clone_record(old_record, config)
            self.db.add(new_record)
            self.db.flush()  # Get new ID

            # Store ID mapping
            if config.creates_mapping:
                self.id_maps[config.creates_mapping][old_record.id] = new_record.id
                logger.debug(f"[CLONE] {table_name}: Mapped {old_record.id} -> {new_record.id}")

            # Clone nested models
            for nested_table in config.nested_models:
                nested_config = BranchCloneRegistry.get(nested_table)
                if nested_config:
                    self._clone_nested(old_record.id, new_record.id, nested_config)

            count += 1

        self.stats[table_name] = count
        logger.info(f"[CLONE] {table_name}: Successfully cloned {count} records")

    def _clone_via_mapping(self, config: BranchCloneConfig) -> None:
        """
        Clone a table by iterating through an FK mapping.

        Used for tables like ChapterSummaryBatch that don't have story_id/branch_id
        but are cloned based on their FK relationship (e.g., chapter_id).
        """
        model_class = config.model_class
        table_name = config.table_name
        mapping_key = config.iterate_via_mapping
        fk_field = config.iterate_fk_field

        if mapping_key not in self.id_maps:
            logger.warning(f"Mapping {mapping_key} not found for {table_name}, skipping")
            return

        count = 0
        for old_fk_id, new_fk_id in self.id_maps[mapping_key].items():
            # Query records for this FK value
            query = self.db.query(model_class).filter(
                getattr(model_class, fk_field) == old_fk_id
            )

            # Apply custom filter if defined
            if config.filter_func:
                query = config.filter_func(
                    query, self.fork_sequence, self.story_id, self.source_branch_id
                )

            for old_record in query.all():
                new_record = self._clone_record(
                    old_record, config,
                    parent_fk_override=(fk_field, new_fk_id)
                )
                self.db.add(new_record)
                count += 1

        self.db.flush()
        self.stats[table_name] = count
        logger.debug(f"Cloned {count} records from {table_name} via {mapping_key}")

    def _clone_record(
        self,
        old_record: Any,
        config: BranchCloneConfig,
        parent_fk_override: Optional[Tuple[str, int]] = None
    ) -> Any:
        """
        Create a new record with remapped FKs.

        Args:
            old_record: The source record to clone
            config: Cloning configuration for this model
            parent_fk_override: Optional (field_name, new_value) to override parent FK

        Returns:
            New model instance (not yet added to session)
        """
        model_class = config.model_class
        mapper = inspect(model_class)

        new_data = {}
        skip_fields = set(STANDARD_SKIP_FIELDS + config.skip_fields)

        for column in mapper.columns:
            col_name = column.name

            if col_name in skip_fields:
                continue

            old_value = getattr(old_record, col_name)

            # Handle branch_id
            if col_name == 'branch_id' and config.has_branch_id:
                new_data[col_name] = self.new_branch_id
                continue

            # Handle parent FK override (for nested models)
            if parent_fk_override and col_name == parent_fk_override[0]:
                new_data[col_name] = parent_fk_override[1]
                continue

            # Handle FK remapping
            if col_name in config.fk_remappings:
                mapping_key = config.fk_remappings[col_name]
                if old_value is not None and mapping_key in self.id_maps:
                    new_data[col_name] = self.id_maps[mapping_key].get(old_value, old_value)
                else:
                    new_data[col_name] = old_value
                continue

            # Handle self-referential FK
            if col_name == config.self_ref_fk and config.creates_mapping:
                if old_value is not None and config.creates_mapping in self.id_maps:
                    new_data[col_name] = self.id_maps[config.creates_mapping].get(old_value)
                else:
                    new_data[col_name] = old_value
                continue

            # Handle deferred FK (store for later update)
            if col_name in config.deferred_fk_remappings:
                # Set to None initially, will be updated after all records are cloned
                new_data[col_name] = None
                if old_value is not None:
                    self.deferred_updates.append({
                        'model_class': model_class,
                        'table_name': config.table_name,
                        'old_record_id': old_record.id,
                        'field': col_name,
                        'old_value': old_value,
                        'mapping_key': config.deferred_fk_remappings[col_name],
                        'creates_mapping': config.creates_mapping,
                    })
                continue

            # Handle special field handlers
            if col_name in config.special_handlers:
                handler = config.special_handlers[col_name]
                new_data[col_name] = handler(old_value, self.new_branch_id)
                continue

            # Handle reset fields
            if col_name in config.reset_fields:
                new_data[col_name] = config.reset_fields[col_name]
                continue

            # Default: copy value as-is
            new_data[col_name] = old_value

        # Apply clone transform if defined
        if config.clone_transform:
            new_data = config.clone_transform(new_data, self.fork_sequence, self.new_branch_id)

        return model_class(**new_data)

    def _clone_nested(
        self,
        old_parent_id: int,
        new_parent_id: int,
        config: BranchCloneConfig
    ) -> None:
        """
        Clone nested records belonging to a parent record.

        Args:
            old_parent_id: ID of the source parent record
            new_parent_id: ID of the new parent record
            config: Cloning configuration for the nested model
        """
        model_class = config.model_class
        parent_field = config.parent_fk_field

        if not parent_field:
            logger.warning(f"Nested model {config.table_name} missing parent_fk_field")
            return

        # Query nested records by parent ID
        query = self.db.query(model_class).filter(
            getattr(model_class, parent_field) == old_parent_id
        )

        # Initialize ID mapping if this nested table creates one
        if config.creates_mapping:
            self.id_maps.setdefault(config.creates_mapping, {})

        nested_count = 0
        for old_record in query.all():
            new_record = self._clone_record(
                old_record, config,
                parent_fk_override=(parent_field, new_parent_id)
            )
            self.db.add(new_record)
            self.db.flush()

            if config.creates_mapping:
                self.id_maps[config.creates_mapping][old_record.id] = new_record.id

            nested_count += 1

        # Update stats
        current_count = self.stats.get(config.table_name, 0)
        self.stats[config.table_name] = current_count + nested_count

    def _apply_deferred_updates(self) -> None:
        """Apply deferred FK updates after all records are cloned."""
        if not self.deferred_updates:
            return

        logger.debug(f"Applying {len(self.deferred_updates)} deferred FK updates")

        for update in self.deferred_updates:
            old_value = update['old_value']
            mapping_key = update['mapping_key']
            creates_mapping = update['creates_mapping']

            if mapping_key not in self.id_maps:
                logger.debug(f"No mapping found for {mapping_key}, skipping deferred update")
                continue

            new_value = self.id_maps[mapping_key].get(old_value)
            if new_value is None:
                # The referenced record wasn't cloned (outside fork point)
                continue

            # Find the new record using the creates_mapping
            if creates_mapping and creates_mapping in self.id_maps:
                old_record_id = update['old_record_id']
                new_record_id = self.id_maps[creates_mapping].get(old_record_id)

                if new_record_id:
                    model_class = update['model_class']
                    field_name = update['field']

                    # Update the record
                    new_record = self.db.query(model_class).filter(
                        model_class.id == new_record_id
                    ).first()

                    if new_record:
                        setattr(new_record, field_name, new_value)
                        logger.debug(f"Updated {update['table_name']}.{field_name}: "
                                   f"{old_value} -> {new_value}")


def clone_branch_data(
    db: Session,
    story_id: int,
    source_branch_id: int,
    new_branch_id: int,
    fork_sequence: int
) -> Dict[str, int]:
    """
    Convenience function to clone all branch-aware data.

    Args:
        db: Database session
        story_id: Story ID
        source_branch_id: Source branch ID to clone from
        new_branch_id: New branch ID to clone to
        fork_sequence: Scene sequence number to fork from

    Returns:
        Dict mapping table names to number of records cloned.
    """
    cloner = BranchCloner(
        db=db,
        story_id=story_id,
        source_branch_id=source_branch_id,
        new_branch_id=new_branch_id,
        fork_sequence=fork_sequence
    )
    return cloner.clone_all()
