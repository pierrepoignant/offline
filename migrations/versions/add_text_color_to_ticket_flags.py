"""add_text_color_to_ticket_flags

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2025-01-27 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add text_color column to crm_ticket_flags table
    op.add_column('crm_ticket_flags', sa.Column('text_color', sa.String(length=7), nullable=True))
    
    # Set default text color to white (#FFFFFF) for existing flags
    op.execute("UPDATE crm_ticket_flags SET text_color = '#FFFFFF' WHERE text_color IS NULL")
    
    # Make text_color NOT NULL after setting defaults
    op.alter_column('crm_ticket_flags', 'text_color', nullable=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # Remove text_color column
    op.drop_column('crm_ticket_flags', 'text_color')
    # ### end Alembic commands ###

