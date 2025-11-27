"""add_scraped_json_rapid_to_asins

Revision ID: f8e7d6c5b4a3
Revises: d2b405171071
Create Date: 2025-11-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8e7d6c5b4a3'
down_revision: Union[str, None] = 'd2b405171071'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add scraped_json_rapid column to asins table
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    
    if 'asins' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('asins')]
        if 'scraped_json_rapid' not in columns:
            op.add_column('asins', sa.Column('scraped_json_rapid', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove scraped_json_rapid column from asins table
    op.drop_column('asins', 'scraped_json_rapid')

