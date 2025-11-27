"""add_netsuite_data_table

Revision ID: 116696b38576
Revises: e5e79e084adb
Create Date: 2025-11-25 18:41:05.595252

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '116696b38576'
down_revision: Union[str, None] = 'e5e79e084adb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create netsuite_data table (if it doesn't already exist)
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    if 'netsuite_data' not in tables:
        op.create_table('netsuite_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('brand_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('revenues', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('units', sa.Integer(), nullable=False),
        sa.Column('retailer_code', sa.String(length=10), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date', 'channel_id', 'item_id', name='uq_netsuite_unique')
        )
        op.create_index('idx_netsuite_brand_date', 'netsuite_data', ['brand_id', 'date'], unique=False)
        op.create_index('idx_netsuite_date', 'netsuite_data', ['date'], unique=False)
        op.create_index('idx_netsuite_item_date', 'netsuite_data', ['item_id', 'date'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # Drop netsuite_data table
    op.drop_index('idx_netsuite_item_date', table_name='netsuite_data')
    op.drop_index('idx_netsuite_date', table_name='netsuite_data')
    op.drop_index('idx_netsuite_brand_date', table_name='netsuite_data')
    op.drop_table('netsuite_data')
    # ### end Alembic commands ###

