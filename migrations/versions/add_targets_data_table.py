"""add_targets_data_table

Revision ID: a2b3c4d5e6f7
Revises: 01d7c42cca20
Create Date: 2025-01-27 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = '01d7c42cca20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create targets_data table
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    
    tables = inspector.get_table_names()
    
    if 'targets_data' not in tables:
        op.create_table('targets_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('brand_id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('revenue', sa.Numeric(12, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index('idx_targets_date', 'targets_data', ['date'], unique=False)
        op.create_index('idx_targets_brand_date', 'targets_data', ['brand_id', 'date'], unique=False)
        op.create_index('idx_targets_channel_date', 'targets_data', ['channel_id', 'date'], unique=False)
        op.create_unique_constraint('uq_targets_unique', 'targets_data', ['date', 'brand_id', 'channel_id'])


def downgrade() -> None:
    # Drop targets_data table
    op.drop_index('idx_targets_channel_date', table_name='targets_data')
    op.drop_index('idx_targets_brand_date', table_name='targets_data')
    op.drop_index('idx_targets_date', table_name='targets_data')
    op.drop_constraint('uq_targets_unique', 'targets_data', type_='unique')
    op.drop_table('targets_data')

