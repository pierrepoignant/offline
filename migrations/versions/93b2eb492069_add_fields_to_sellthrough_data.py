"""add_fields_to_sellthrough_data

Revision ID: 93b2eb492069
Revises: e4f5a6b7c8d9
Create Date: 2025-12-04 19:09:53.886524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '93b2eb492069'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add usd_pspw column (USD per store per week)
    op.add_column('sellthrough_data', sa.Column('usd_pspw', sa.Numeric(12, 2), nullable=True))
    
    # Add units_pspw column (Units per store per week)
    op.add_column('sellthrough_data', sa.Column('units_pspw', sa.Numeric(10, 2), nullable=True))
    
    # Add instock column (In stock percentage)
    op.add_column('sellthrough_data', sa.Column('instock', sa.Numeric(5, 2), nullable=True))
    
    # Add channel_code column
    op.add_column('sellthrough_data', sa.Column('channel_code', sa.String(length=255), nullable=True))


def downgrade() -> None:
    # Remove the added columns
    op.drop_column('sellthrough_data', 'channel_code')
    op.drop_column('sellthrough_data', 'instock')
    op.drop_column('sellthrough_data', 'units_pspw')
    op.drop_column('sellthrough_data', 'usd_pspw')

