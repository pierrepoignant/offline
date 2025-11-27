"""add_code_field_to_brands_table

Revision ID: e5e79e084adb
Revises: 2a913d7c8f7d
Create Date: 2025-11-25 14:54:32.305056

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5e79e084adb'
down_revision: Union[str, None] = '2a913d7c8f7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add code column to brands table
    op.add_column('brands', sa.Column('code', sa.String(length=255), nullable=True))
    # Create unique index on code column
    op.create_unique_constraint('uq_brands_code', 'brands', ['code'])


def downgrade() -> None:
    # Remove unique constraint on code column
    op.drop_constraint('uq_brands_code', 'brands', type_='unique')
    # Drop code column from brands table
    op.drop_column('brands', 'code')

