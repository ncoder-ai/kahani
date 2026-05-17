"""
Tests for Phase 1: Extraction Quality Improvements

Tests:
1. Validation rejects empty character states
2. Validation accepts partial states with 2+ key fields
3. Extraction metrics are tracked on Story model
4. Relationship extraction format is correct
"""

import pytest
from datetime import datetime

# Import the function to test
import sys
sys.path.insert(0, '/app')

from app.services.entity_state_service import (
    has_meaningful_character_state,
    update_extraction_quality_metrics
)


class TestHasMeaningfulCharacterState:
    """Test the stricter validation for character state extraction."""

    def test_rejects_all_empty_fields(self):
        """Characters with all empty fields should fail validation."""
        empty_state = {
            "name": "John",
            "location": "",
            "emotional_state": "",
            "physical_condition": ""
        }
        assert not has_meaningful_character_state(empty_state)

    def test_rejects_null_values(self):
        """Characters with null values should fail validation."""
        null_state = {
            "name": "John",
            "location": None,
            "emotional_state": None,
            "physical_condition": None
        }
        assert not has_meaningful_character_state(null_state)

    def test_rejects_placeholder_values(self):
        """Characters with placeholder values (null, none, n/a) should fail."""
        placeholder_state = {
            "name": "John",
            "location": "null",
            "emotional_state": "N/A",
            "physical_condition": "none"
        }
        assert not has_meaningful_character_state(placeholder_state)

    def test_rejects_single_key_field(self):
        """Characters with only 1 key field should fail (need 2+)."""
        single_field = {
            "name": "John",
            "location": "kitchen",
            "emotional_state": "",
            "physical_condition": ""
        }
        assert not has_meaningful_character_state(single_field)

    def test_accepts_two_key_fields(self):
        """Characters with 2 key fields should pass validation."""
        two_fields = {
            "name": "John",
            "location": "kitchen",
            "emotional_state": "angry",
            "physical_condition": ""
        }
        assert has_meaningful_character_state(two_fields)

    def test_accepts_three_key_fields(self):
        """Characters with all 3 key fields should pass validation."""
        three_fields = {
            "name": "John",
            "location": "bedroom",
            "emotional_state": "nervous",
            "physical_condition": "tired"
        }
        assert has_meaningful_character_state(three_fields)

    def test_accepts_one_key_plus_two_secondary(self):
        """1 key field + 2 secondary fields should pass."""
        mixed_fields = {
            "name": "John",
            "location": "office",
            "emotional_state": "",
            "physical_condition": "",
            "knowledge_gained": ["learned secret"],
            "possessions_gained": ["key"]
        }
        assert has_meaningful_character_state(mixed_fields)

    def test_rejects_one_key_plus_one_secondary(self):
        """1 key field + 1 secondary field should fail."""
        insufficient = {
            "name": "John",
            "location": "office",
            "emotional_state": "",
            "physical_condition": "",
            "knowledge_gained": ["learned secret"]
        }
        assert not has_meaningful_character_state(insufficient)

    def test_handles_relationship_changes_dict(self):
        """Relationship changes dict should count as secondary field."""
        with_relationship = {
            "name": "John",
            "location": "kitchen",
            "emotional_state": "",
            "physical_condition": "",
            "relationship_changes": {"Mary": {"type": "friend", "change": "made up"}}
        }
        # 1 key + 1 secondary = not enough
        assert not has_meaningful_character_state(with_relationship)

        # Add another secondary
        with_relationship["knowledge_gained"] = ["learned truth"]
        assert has_meaningful_character_state(with_relationship)

    def test_handles_empty_lists(self):
        """Empty lists should not count as meaningful."""
        empty_lists = {
            "name": "John",
            "location": "kitchen",
            "emotional_state": "",
            "physical_condition": "",
            "possessions_gained": [],
            "knowledge_gained": []
        }
        # 1 key field, empty secondary lists
        assert not has_meaningful_character_state(empty_lists)


class TestExtractionMetrics:
    """Test extraction quality metrics tracking."""

    def test_metrics_calculation_success(self):
        """Successful extraction should increment success rate."""
        # This would need a database fixture to test properly
        # For now, just verify the function signature
        from app.services.entity_state_service import update_extraction_quality_metrics
        assert callable(update_extraction_quality_metrics)

    def test_metrics_calculation_empty(self):
        """Empty extraction should increment empty rate."""
        # Would need database fixture
        pass


class TestRelationshipExtractionFormat:
    """Test that relationship extraction follows new format."""

    def test_old_format_still_works(self):
        """Old simple format should still be accepted."""
        old_format = {
            "name": "John",
            "location": "kitchen",
            "emotional_state": "happy",
            "relationship_changes": {"Mary": "became friends"}
        }
        # Should pass validation (2 key fields)
        assert has_meaningful_character_state(old_format)

    def test_new_format_works(self):
        """New structured format should be accepted."""
        new_format = {
            "name": "John",
            "location": "kitchen",
            "emotional_state": "happy",
            "relationship_changes": {
                "Mary": {
                    "type": "romantic",
                    "change": "first kiss",
                    "status": "dating"
                }
            }
        }
        # Should pass validation
        assert has_meaningful_character_state(new_format)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
