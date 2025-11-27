"""Make essor_code and essor_name nullable in items table

Revision ID: 2a913d7c8f7d
Revises: 157ff59550e5
Create Date: 2025-11-25 11:53:53.860898

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2a913d7c8f7d'
down_revision: Union[str, None] = '157ff59550e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make essor_code and essor_name nullable in items table
    op.alter_column('items', 'essor_code',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    op.alter_column('items', 'essor_name',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # Make essor_code and essor_name NOT NULL again
    op.alter_column('items', 'essor_name',
               existing_type=sa.VARCHAR(length=255),
               nullable=False)
    op.alter_column('items', 'essor_code',
               existing_type=sa.VARCHAR(length=255),
               nullable=False)
    # ### end Alembic commands ###

