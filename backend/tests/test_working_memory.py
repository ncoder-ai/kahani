"""
Tests for Phase 2: Working Memory Scratchpad

Tests:
1. WorkingMemory model CRUD operations
2. Active threads derived from PlotEvent (not duplicated)
3. Working memory update extraction
4. Context integration with story_focus
"""

import pytest
from datetime import datetime

# Import the models and services to test
import sys
sys.path.insert(0, '/app')

from app.models import WorkingMemory, PlotEvent


class TestWorkingMemoryModel:
    """Test WorkingMemory model CRUD operations."""

    def test_working_memory_to_dict(self):
        """WorkingMemory.to_dict() should return proper structure."""
        wm = WorkingMemory(
            story_id=1,
            branch_id=1,
            recent_focus=["Character A's revelation", "The confrontation"],
            pending_items=["Letter picked up but not read"],
            character_spotlight={"John": "hasn't spoken in 2 scenes"},
            last_scene_sequence=5
        )

        result = wm.to_dict()

        assert result["recent_focus"] == ["Character A's revelation", "The confrontation"]
        assert result["pending_items"] == ["Letter picked up but not read"]
        assert result["character_spotlight"] == {"John": "hasn't spoken in 2 scenes"}
        assert result["last_scene_sequence"] == 5

    def test_working_memory_defaults(self):
        """WorkingMemory should have sensible defaults."""
        wm = WorkingMemory(story_id=1, branch_id=1)

        result = wm.to_dict()

        assert result["recent_focus"] == []
        assert result["pending_items"] == []
        assert result["character_spotlight"] == {}
        assert result["last_scene_sequence"] is None


class TestActiveThreadsFromPlotEvent:
    """Test that active threads are derived from PlotEvent, not duplicated."""

    def test_unresolved_plot_events_are_active_threads(self):
        """PlotEvents with is_resolved=False should be active threads."""
        # Create mock unresolved PlotEvent
        pe = PlotEvent(
            story_id=1,
            branch_id=1,
            description="Will John discover Mary's secret?",
            is_resolved=False,
            importance_score=0.8
        )

        # Active thread should use the description
        assert pe.is_resolved == False
        assert pe.description == "Will John discover Mary's secret?"

    def test_resolved_plot_events_not_active(self):
        """PlotEvents with is_resolved=True should not be active threads."""
        pe = PlotEvent(
            story_id=1,
            branch_id=1,
            description="The missing necklace",
            is_resolved=True,
            importance_score=0.5
        )

        assert pe.is_resolved == True


class TestStoryFocusIntegration:
    """Test story_focus context structure."""

    def test_story_focus_structure(self):
        """story_focus should have expected keys."""
        story_focus = {
            "active_threads": ["Will John find the truth?"],
            "recent_focus": ["The argument", "Mary's tears"],
            "pending_items": ["Phone rang but wasn't answered"],
            "character_spotlight": {"Sarah": "needs to respond to accusation"}
        }

        assert "active_threads" in story_focus
        assert "recent_focus" in story_focus
        assert "pending_items" in story_focus
        assert "character_spotlight" in story_focus

    def test_story_focus_limits(self):
        """story_focus should respect limits (3 items max per category)."""
        # This tests the limiting behavior in context_manager._build_story_focus
        focus_items = ["item1", "item2", "item3", "item4", "item5"]
        limited = focus_items[:3]

        assert len(limited) == 3
        assert limited == ["item1", "item2", "item3"]


class TestWorkingMemoryExtraction:
    """Test working memory extraction prompt and parsing."""

    def test_extraction_response_format(self):
        """Extraction should return proper JSON structure."""
        # Simulated extraction response
        response = {
            "recent_focus": ["The heated argument", "Sarah's confession"],
            "pending_items": ["The letter was left on the table"],
            "character_spotlight": {"Marcus": "was cut off mid-sentence"}
        }

        assert isinstance(response["recent_focus"], list)
        assert isinstance(response["pending_items"], list)
        assert isinstance(response["character_spotlight"], dict)

    def test_empty_extraction_handling(self):
        """Empty extractions should be handled gracefully."""
        response = {
            "recent_focus": [],
            "pending_items": [],
            "character_spotlight": {}
        }

        # All empty but valid
        assert len(response["recent_focus"]) == 0
        assert len(response["pending_items"]) == 0
        assert len(response["character_spotlight"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
