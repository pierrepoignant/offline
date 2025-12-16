"""add_faire_data_table

Revision ID: d3e4f5a6b7c8
Revises: c4d5e6f7a8b9
Create Date: 2025-01-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create faire_data table
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    
    tables = inspector.get_table_names()
    
    if 'faire_data' not in tables:
        op.create_table('faire_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('brand_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('revenues', sa.Numeric(12, 2), nullable=False),
        sa.Column('units', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], ),
        sa.ForeignKeyConstraint(['customer_id'], ['channel_customers.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index('idx_faire_date', 'faire_data', ['date'], unique=False)
        op.create_index('idx_faire_brand_date', 'faire_data', ['brand_id', 'date'], unique=False)
        op.create_index('idx_faire_item_date', 'faire_data', ['item_id', 'date'], unique=False)
        op.create_unique_constraint('uq_faire_unique', 'faire_data', ['date', 'item_id', 'customer_id'])


def downgrade() -> None:
    # Drop faire_data table
    op.drop_index('idx_faire_item_date', table_name='faire_data')
    op.drop_index('idx_faire_brand_date', table_name='faire_data')
    op.drop_index('idx_faire_date', table_name='faire_data')
    op.drop_constraint('uq_faire_unique', 'faire_data', type_='unique')
    op.drop_table('faire_data')

