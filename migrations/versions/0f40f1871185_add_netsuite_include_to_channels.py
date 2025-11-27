"""add_netsuite_include_to_channels

Revision ID: 0f40f1871185
Revises: cb7ac58d8e4f
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f40f1871185'
down_revision: Union[str, None] = 'cb7ac58d8e4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add netsuite_include column to channels table
    op.add_column('channels', sa.Column('netsuite_include', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    # ### end Alembic commands ###


def downgrade() -> None:
    # Remove netsuite_include column from channels table
    op.drop_column('channels', 'netsuite_include')
    # ### end Alembic commands ###

