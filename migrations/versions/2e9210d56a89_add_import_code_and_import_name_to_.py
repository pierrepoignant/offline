"""add_import_code_and_import_name_to_channel_customers

Revision ID: 2e9210d56a89
Revises: 879548d54746
Create Date: 2025-11-25 19:41:39.965956

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2e9210d56a89'
down_revision: Union[str, None] = '879548d54746'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add import_code and import_name columns to channel_customers table
    # Check if table exists (it might still be channel_locations if previous migration didn't run)
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    table_name = 'channel_customers'
    if 'channel_customers' not in tables and 'channel_locations' in tables:
        table_name = 'channel_locations'
    
    op.add_column(table_name, sa.Column('import_code', sa.String(length=255), nullable=True))
    op.add_column(table_name, sa.Column('import_name', sa.String(length=255), nullable=True))


def downgrade() -> None:
    # Remove import_code and import_name columns from channel_customers table
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    table_name = 'channel_customers'
    if 'channel_customers' not in tables and 'channel_locations' in tables:
        table_name = 'channel_locations'
    
    op.drop_column(table_name, 'import_name')
    op.drop_column(table_name, 'import_code')

