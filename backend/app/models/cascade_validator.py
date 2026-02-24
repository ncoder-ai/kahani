"""
Startup validator: ensures every NOT NULL FK pointing at a parent table
has a matching cascade="all, delete-orphan" relationship on the parent.

Without this, SQLAlchemy tries to SET NULL before deleting the parent,
which violates the NOT NULL constraint and silently breaks deletion.
"""

import logging
from sqlalchemy import inspect as sa_inspect
from ..database import Base

logger = logging.getLogger(__name__)

# Parent tables whose deletion must cascade cleanly
PROTECTED_PARENTS = {"stories", "scenes", "chapters"}


def validate_cascade_relationships() -> list[str]:
    """
    Walk every mapped class. For each NOT NULL FK that points at a
    PROTECTED_PARENTS table, verify the parent model has a relationship
    with cascade="all, delete-orphan" (or at least "delete") covering
    that child table.

    Returns a list of error strings (empty = all good).
    """
    errors: list[str] = []

    # Build a map: parent_table -> set of child tables covered by cascade relationships
    parent_cascade_targets: dict[str, set[str]] = {t: set() for t in PROTECTED_PARENTS}

    # First pass: collect all cascade relationships from parent models
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        table = mapper.local_table
        if table is None:
            continue
        table_name = table.name
        if table_name not in PROTECTED_PARENTS:
            continue

        for rel in mapper.relationships:
            cascade = rel.cascade
            # Check if this relationship has delete cascade
            if cascade.delete or cascade.delete_orphan:
                target_table = rel.mapper.local_table
                if target_table is not None:
                    parent_cascade_targets[table_name].add(target_table.name)

    # Second pass: find NOT NULL FKs pointing at protected parents without coverage
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        table = mapper.local_table
        if table is None:
            continue

        for col in table.columns:
            if not col.foreign_keys:
                continue
            if col.nullable:
                continue  # Nullable FKs are fine — SQLAlchemy can SET NULL

            for fk in col.foreign_keys:
                parent_table = fk.column.table.name
                if parent_table not in PROTECTED_PARENTS:
                    continue

                child_table = table.name
                if child_table == parent_table:
                    continue  # Self-referential (e.g. parent_scene_id) — skip

                if child_table not in parent_cascade_targets[parent_table]:
                    errors.append(
                        f"Table '{child_table}.{col.name}' has NOT NULL FK to "
                        f"'{parent_table}' but the parent model for '{parent_table}' "
                        f"has no cascade relationship covering '{child_table}'. "
                        f"Add: {child_table} = relationship(\"{cls.__name__}\", ..., "
                        f"cascade=\"all, delete-orphan\") to the parent model."
                    )

    return errors
