"""add_brand_id_to_channel_customers

Revision ID: a1b2c3d4e5f6
Revises: f8e7d6c5b4a3
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f8e7d6c5b4a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add brand_id column to channel_customers table
    op.add_column('channel_customers', sa.Column('brand_id', sa.Integer(), nullable=True))
    # Create foreign key constraint
    op.create_foreign_key('channel_customers_brand_id_fkey', 'channel_customers', 'brands', ['brand_id'], ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # Remove foreign key constraint
    op.drop_constraint('channel_customers_brand_id_fkey', 'channel_customers', type_='foreignkey')
    # Remove brand_id column from channel_customers table
    op.drop_column('channel_customers', 'brand_id')
    # ### end Alembic commands ###

