"""add_color_to_customer_types

Revision ID: f9a8b7c6d5e4
Revises: 8c279fc36cbf
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9a8b7c6d5e4'
down_revision: Union[str, None] = '8c279fc36cbf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add color column to channel_customer_types table
    op.add_column('channel_customer_types', sa.Column('color', sa.String(length=7), nullable=True))


def downgrade() -> None:
    # Drop color column from channel_customer_types table
    op.drop_column('channel_customer_types', 'color')

