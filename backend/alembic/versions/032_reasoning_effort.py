"""Add reasoning_effort and show_thinking_content to user_settings

Revision ID: 032_reasoning_effort
Revises: 031_plot_event_extraction_threshold
Create Date: 2026-01-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '032_reasoning_effort'
down_revision = '031_plot_event_threshold'
branch_labels = None
depends_on = None


def upgrade():
    # Add reasoning_effort column - controls how much the model "thinks"
    # Values: None (auto), "disabled", "low", "medium", "high"
    op.add_column('user_settings', sa.Column('reasoning_effort', sa.String(20), nullable=True))
    
    # Add show_thinking_content column - whether to display thinking text in UI
    # True = show full thinking content in collapsible box
    # False = just show "Thinking..." indicator
    op.add_column('user_settings', sa.Column('show_thinking_content', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('user_settings', 'show_thinking_content')
    op.drop_column('user_settings', 'reasoning_effort')

