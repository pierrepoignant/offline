"""add_domain_to_spins_brands

Revision ID: 01d7c42cca20
Revises: a1b2c3d4e5f7
Create Date: 2025-11-27 15:27:35.790524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01d7c42cca20'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add domain column to spins_brands table
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    
    if 'spins_brands' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('spins_brands')]
        
        if 'domain' not in columns:
            op.add_column('spins_brands', sa.Column('domain', sa.String(length=255), nullable=True))


def downgrade() -> None:
    # Remove domain column from spins_brands table
    op.drop_column('spins_brands', 'domain')

