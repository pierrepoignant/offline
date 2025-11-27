"""add_import_errors_table

Revision ID: d82037aa896c
Revises: 116696b38576
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd82037aa896c'
down_revision: Union[str, None] = '41fe64feb14f'  # After add_internal_id_to_netsuite_data
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create import_errors table
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    if 'import_errors' not in tables:
        op.create_table('import_errors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('import_channel', sa.String(length=50), nullable=False),
        sa.Column('import_date', sa.DateTime(), nullable=False),
        sa.Column('error_data', sa.Text(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('row_number', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index('idx_import_error_channel_date', 'import_errors', ['import_channel', 'import_date'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # Drop import_errors table
    op.drop_index('idx_import_error_channel_date', table_name='import_errors')
    op.drop_table('import_errors')
    # ### end Alembic commands ###

