"""rename_locations_to_customers_and_update_foreign_keys

Revision ID: 879548d54746
Revises: 79a49cd94416
Create Date: 2025-11-25 19:38:44.765022

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '879548d54746'
down_revision: Union[str, None] = '79a49cd94416'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename table channel_locations to channel_customers
    op.rename_table('channel_locations', 'channel_customers')
    
    # Rename the unique constraint
    op.drop_constraint('uq_location_channel', 'channel_customers', type_='unique')
    op.create_unique_constraint('uq_customer_channel', 'channel_customers', ['name', 'channel_id'])
    
    # Rename location_id to customer_id in sellthrough_data
    op.alter_column('sellthrough_data', 'location_id', new_column_name='customer_id')
    
    # Drop old foreign key and create new one
    op.drop_constraint('sellthrough_data_location_id_fkey', 'sellthrough_data', type_='foreignkey')
    op.create_foreign_key('sellthrough_data_customer_id_fkey', 'sellthrough_data', 'channel_customers', ['customer_id'], ['id'])
    
    # Drop old unique constraint and create new one with customer_id
    op.drop_constraint('uq_sellthrough_unique', 'sellthrough_data', type_='unique')
    op.create_unique_constraint('uq_sellthrough_unique', 'sellthrough_data', ['date', 'channel_id', 'item_id', 'customer_id'])
    
    # Add customer_id column to netsuite_data
    op.add_column('netsuite_data', sa.Column('customer_id', sa.Integer(), nullable=True))
    
    # Create foreign key for customer_id in netsuite_data
    op.create_foreign_key('netsuite_data_customer_id_fkey', 'netsuite_data', 'channel_customers', ['customer_id'], ['id'])
    
    # Drop old unique constraint and create new one with customer_id
    op.drop_constraint('uq_netsuite_unique', 'netsuite_data', type_='unique')
    op.create_unique_constraint('uq_netsuite_unique', 'netsuite_data', ['date', 'channel_id', 'item_id', 'customer_id'])


def downgrade() -> None:
    # Revert netsuite_data changes
    op.drop_constraint('uq_netsuite_unique', 'netsuite_data', type_='unique')
    op.create_unique_constraint('uq_netsuite_unique', 'netsuite_data', ['date', 'channel_id', 'item_id'])
    op.drop_constraint('netsuite_data_customer_id_fkey', 'netsuite_data', type_='foreignkey')
    op.drop_column('netsuite_data', 'customer_id')
    
    # Revert sellthrough_data changes
    op.drop_constraint('uq_sellthrough_unique', 'sellthrough_data', type_='unique')
    op.create_unique_constraint('uq_sellthrough_unique', 'sellthrough_data', ['date', 'channel_id', 'item_id', 'location_id'])
    op.drop_constraint('sellthrough_data_customer_id_fkey', 'sellthrough_data', type_='foreignkey')
    op.create_foreign_key('sellthrough_data_location_id_fkey', 'sellthrough_data', 'channel_locations', ['location_id'], ['id'])
    op.alter_column('sellthrough_data', 'customer_id', new_column_name='location_id')
    
    # Revert table rename
    op.drop_constraint('uq_customer_channel', 'channel_customers', type_='unique')
    op.create_unique_constraint('uq_location_channel', 'channel_customers', ['name', 'channel_id'])
    op.rename_table('channel_customers', 'channel_locations')
