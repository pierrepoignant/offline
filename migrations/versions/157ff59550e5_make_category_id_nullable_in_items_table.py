"""Make category_id nullable in items table

Revision ID: 157ff59550e5
Revises: 53831f8bc629
Create Date: 2025-11-25 11:13:47.248802

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '157ff59550e5'
down_revision: Union[str, None] = '53831f8bc629'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make category_id nullable in items table
    op.alter_column('items', 'category_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # Make category_id NOT NULL again (requires all items to have a category)
    op.alter_column('items', 'category_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    # ### end Alembic commands ###

