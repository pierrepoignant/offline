"""make_item_id_and_brand_id_nullable_in_sellthrough_data

Revision ID: 5b384bdc9357
Revises: 93b2eb492069
Create Date: 2025-12-05 06:30:21.567916

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b384bdc9357'
down_revision: Union[str, None] = '93b2eb492069'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make item_id and brand_id nullable
    op.alter_column('sellthrough_data', 'item_id', nullable=True)
    op.alter_column('sellthrough_data', 'brand_id', nullable=True)
    
    # Drop the old unique constraint
    op.drop_constraint('uq_sellthrough_unique', 'sellthrough_data', type_='unique')
    
    # Create unique indexes with WHERE clauses for NULL and non-NULL cases
    # For rows with item_id (NOT NULL), use the original constraint
    op.create_index(
        'uq_sellthrough_with_item',
        'sellthrough_data',
        ['date', 'channel_id', 'item_id', 'customer_id'],
        unique=True,
        postgresql_where=sa.text('item_id IS NOT NULL')
    )
    # For rows without item_id (NULL), use channel_code for uniqueness
    op.create_index(
        'uq_sellthrough_without_item',
        'sellthrough_data',
        ['date', 'channel_id', 'channel_code', 'customer_id'],
        unique=True,
        postgresql_where=sa.text('item_id IS NULL')
    )


def downgrade() -> None:
    # Drop the new indexes
    op.drop_index('uq_sellthrough_without_item', 'sellthrough_data')
    op.drop_index('uq_sellthrough_with_item', 'sellthrough_data')
    
    # Recreate the old unique constraint
    op.create_unique_constraint('uq_sellthrough_unique', 'sellthrough_data', ['date', 'channel_id', 'item_id', 'customer_id'])
    
    # Make item_id and brand_id NOT NULL again (this might fail if there are NULL values)
    op.alter_column('sellthrough_data', 'item_id', nullable=False)
    op.alter_column('sellthrough_data', 'brand_id', nullable=False)

