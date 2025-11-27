"""add_scraping_fields_to_spins_items

Revision ID: a1b2c3d4e5f7
Revises: f9a8b7c6d5e4
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'f9a8b7c6d5e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add scraping fields to spins_items table
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    
    if 'spins_items' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('spins_items')]
        
        if 'img_url' not in columns:
            op.add_column('spins_items', sa.Column('img_url', sa.String(length=500), nullable=True))
        
        if 'scrapped_name' not in columns:
            op.add_column('spins_items', sa.Column('scrapped_name', sa.String(length=500), nullable=True))
        
        if 'scrapped_url' not in columns:
            op.add_column('spins_items', sa.Column('scrapped_url', sa.String(length=500), nullable=True))
        
        if 'scrapped_json' not in columns:
            op.add_column('spins_items', sa.Column('scrapped_json', sa.Text(), nullable=True))
        
        if 'scrapped_at' not in columns:
            op.add_column('spins_items', sa.Column('scrapped_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove scraping fields from spins_items table
    op.drop_column('spins_items', 'scrapped_at')
    op.drop_column('spins_items', 'scrapped_json')
    op.drop_column('spins_items', 'scrapped_url')
    op.drop_column('spins_items', 'scrapped_name')
    op.drop_column('spins_items', 'img_url')

