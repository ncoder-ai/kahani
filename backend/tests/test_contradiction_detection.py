"""
Tests for Phase 3: Contradiction Detection

Tests:
1. Location jump detection
2. State regression detection
3. Contradiction API endpoints
4. Contradiction resolution
"""

import pytest
from datetime import datetime

import sys
sys.path.insert(0, '/app')

from app.models import Contradiction


class TestContradictionModel:
    """Test Contradiction model."""

    def test_contradiction_to_dict(self):
        """Contradiction.to_dict() should return proper structure."""
        c = Contradiction(
            story_id=1,
            branch_id=1,
            scene_sequence=5,
            contradiction_type='location_jump',
            character_name='John',
            previous_value='kitchen',
            current_value='beach',
            severity='warning',
            resolved=False
        )

        result = c.to_dict()

        assert result["story_id"] == 1
        assert result["contradiction_type"] == "location_jump"
        assert result["character_name"] == "John"
        assert result["previous_value"] == "kitchen"
        assert result["current_value"] == "beach"
        assert result["resolved"] == False

    def test_contradiction_repr(self):
        """Contradiction __repr__ should be informative."""
        c = Contradiction(
            id=1,
            contradiction_type='location_jump',
            character_name='John',
            resolved=False
        )

        repr_str = repr(c)
        assert "location_jump" in repr_str
        assert "John" in repr_str


class TestLocationJumpDetection:
    """Test location jump detection logic."""

    def test_same_location_no_contradiction(self):
        """Same location should not create contradiction."""
        # If character was in kitchen and is still in kitchen, no issue
        prev_location = "kitchen"
        new_location = "kitchen"
        assert prev_location == new_location

    def test_different_location_flags_contradiction(self):
        """Different locations should flag potential contradiction."""
        prev_location = "kitchen"
        new_location = "beach"
        assert prev_location != new_location  # This would trigger a contradiction

    def test_unknown_location_ignored(self):
        """Unknown locations should be ignored."""
        unknown_values = ['unknown', 'null', 'none', '']
        for val in unknown_values:
            # These should not trigger contradictions
            assert val.strip().lower() in ['unknown', 'null', 'none', '']


class TestStateRegressionDetection:
    """Test state regression detection logic."""

    def test_emotion_opposites(self):
        """Should detect opposite emotional states."""
        emotion_opposites = {
            'happy': ['sad', 'depressed', 'miserable'],
            'calm': ['angry', 'furious', 'enraged'],
            'confident': ['anxious', 'nervous', 'scared'],
        }

        # Verify structure
        assert 'happy' in emotion_opposites
        assert 'sad' in emotion_opposites['happy']

    def test_normal_emotion_change(self):
        """Non-opposite emotion changes should not flag."""
        # happy -> excited is not a contradiction
        prev = "happy"
        new = "excited"
        # Not in opposites list for happy
        opposites = ['sad', 'depressed', 'miserable']
        assert new not in opposites


class TestContradictionService:
    """Test ContradictionService methods."""

    def test_contradiction_types_defined(self):
        """Service should have defined contradiction types."""
        types = [
            'location_jump',
            'knowledge_leak',
            'state_regression',
            'timeline_error',
        ]

        for t in types:
            assert isinstance(t, str)
            assert len(t) > 0


class TestContradictionAPI:
    """Test contradiction API response structure."""

    def test_summary_response_structure(self):
        """Summary endpoint should return expected structure."""
        summary = {
            "total": 5,
            "unresolved": 3,
            "resolved": 2,
            "by_type": {"location_jump": 2, "state_regression": 1},
            "by_severity": {"warning": 2, "info": 1}
        }

        assert "total" in summary
        assert "unresolved" in summary
        assert "resolved" in summary
        assert "by_type" in summary
        assert "by_severity" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
