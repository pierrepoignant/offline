"""add_description_to_channel_customers

Revision ID: a1b2c3d4e5f7
Revises: 0f40f1871185
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c1f31866804'
down_revision: Union[str, None] = '0f40f1871185'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add description column to channel_customers table
    op.add_column('channel_customers', sa.Column('description', sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # Remove description column from channel_customers table
    op.drop_column('channel_customers', 'description')
    # ### end Alembic commands ###

