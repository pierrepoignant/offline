"""make_channel_id_nullable_in_netsuite_tables

Revision ID: 3c9764a8682f
Revises: 81ab157d3fc4
Create Date: 2025-11-25 20:16:45.589881

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c9764a8682f'
down_revision: Union[str, None] = '81ab157d3fc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make channel_id nullable in netsuite_codes
    op.alter_column('netsuite_codes', 'channel_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    
    # Make channel_id nullable in netsuite_data
    op.alter_column('netsuite_data', 'channel_id',
               existing_type=sa.INTEGER(),
               nullable=True)


def downgrade() -> None:
    # Revert channel_id to NOT NULL in netsuite_data
    op.alter_column('netsuite_data', 'channel_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    
    # Revert channel_id to NOT NULL in netsuite_codes
    op.alter_column('netsuite_codes', 'channel_id',
               existing_type=sa.INTEGER(),
               nullable=False)

