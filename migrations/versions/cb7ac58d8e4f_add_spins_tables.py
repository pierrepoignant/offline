"""add_spins_tables

Revision ID: a1b2c3d4e5f6
Revises: d82037aa896c
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb7ac58d8e4f'
down_revision: Union[str, None] = 'd82037aa896c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create spins_channels table
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    if 'spins_channels' not in tables:
        op.create_table('spins_channels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('short_name', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_spins_channel_name')
        )
    
    # Create spins_brands table
    if 'spins_brands' not in tables:
        op.create_table('spins_brands',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('short_name', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_spins_brand_name')
        )
    
    # Create spins_items table
    if 'spins_items' not in tables:
        op.create_table('spins_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('short_name', sa.String(length=100), nullable=True),
        sa.Column('upc', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('upc', name='uq_spins_item_upc')
        )
        op.create_index('idx_spins_item_upc', 'spins_items', ['upc'], unique=False)
    
    # Create spins_data table
    if 'spins_data' not in tables:
        op.create_table('spins_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('week', sa.Date(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('brand_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('stores_total', sa.Integer(), nullable=False),
        sa.Column('stores_selling', sa.Numeric(precision=10, scale=1), nullable=False),
        sa.Column('revenues', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('units', sa.Integer(), nullable=False),
        sa.Column('arp', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('average_weekly_revenues_per_selling_item', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('average_weekly_units_per_selling_item', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['spins_channels.id'], ),
        sa.ForeignKeyConstraint(['brand_id'], ['spins_brands.id'], ),
        sa.ForeignKeyConstraint(['item_id'], ['spins_items.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('week', 'channel_id', 'brand_id', 'item_id', name='uq_spins_unique')
        )
        op.create_index('idx_spins_week', 'spins_data', ['week'], unique=False)
        op.create_index('idx_spins_channel_week', 'spins_data', ['channel_id', 'week'], unique=False)
        op.create_index('idx_spins_brand_week', 'spins_data', ['brand_id', 'week'], unique=False)
        op.create_index('idx_spins_item_week', 'spins_data', ['item_id', 'week'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # Drop spins_data table
    op.drop_index('idx_spins_item_week', table_name='spins_data')
    op.drop_index('idx_spins_brand_week', table_name='spins_data')
    op.drop_index('idx_spins_channel_week', table_name='spins_data')
    op.drop_index('idx_spins_week', table_name='spins_data')
    op.drop_table('spins_data')
    
    # Drop spins_items table
    op.drop_index('idx_spins_item_upc', table_name='spins_items')
    op.drop_table('spins_items')
    
    # Drop spins_brands table
    op.drop_table('spins_brands')
    
    # Drop spins_channels table
    op.drop_table('spins_channels')
    # ### end Alembic commands ###

