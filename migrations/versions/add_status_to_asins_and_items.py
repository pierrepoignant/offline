"""add_status_to_asins_and_items

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2025-01-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add status column to asins table
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    
    if 'asins' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('asins')]
        
        if 'status' not in columns:
            op.add_column('asins', sa.Column('status', sa.String(length=255), nullable=True))
    
    # Add status column to items table
    if 'items' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('items')]
        
        if 'status' not in columns:
            op.add_column('items', sa.Column('status', sa.String(length=255), nullable=True))


def downgrade() -> None:
    # Remove status column from items table
    op.drop_column('items', 'status')
    
    # Remove status column from asins table
    op.drop_column('asins', 'status')

