"""Add channel_items table

Revision ID: 53831f8bc629
Revises: 
Create Date: 2025-11-25 11:07:49.008491

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '53831f8bc629'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create channel_items table (if it doesn't already exist)
    # This handles the case where the table was created manually before the migration
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    if 'channel_items' not in tables:
        op.create_table('channel_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('channel_code', sa.String(length=255), nullable=False),
        sa.Column('channel_name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('channel_id', 'item_id', name='uq_channel_item')
        )
    # ### end Alembic commands ###


def downgrade() -> None:
    # Drop channel_items table
    op.drop_table('channel_items')
    # ### end Alembic commands ###

