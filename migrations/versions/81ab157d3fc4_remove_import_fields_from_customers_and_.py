"""remove_import_fields_from_customers_and_rename_retailer_codes_to_netsuite_codes

Revision ID: 81ab157d3fc4
Revises: 2e9210d56a89
Create Date: 2025-11-25 20:06:42.686634

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '81ab157d3fc4'
down_revision: Union[str, None] = '2e9210d56a89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove import_code and import_name from channel_customers
    op.drop_column('channel_customers', 'import_name')
    op.drop_column('channel_customers', 'import_code')
    
    # Rename table retailer_codes to netsuite_codes
    op.rename_table('retailer_codes', 'netsuite_codes')
    
    # Rename sequence
    op.execute("ALTER SEQUENCE retailer_codes_id_seq RENAME TO netsuite_codes_id_seq")
    
    # Rename column retailer_code to netsuite_code
    op.alter_column('netsuite_codes', 'retailer_code', new_column_name='netsuite_code')
    
    # Rename index
    op.drop_index('idx_retailer_code', table_name='netsuite_codes')
    op.create_index('idx_netsuite_code', 'netsuite_codes', ['netsuite_code'], unique=False)
    
    # Rename unique constraint
    op.drop_constraint('uq_retailer_code', 'netsuite_codes', type_='unique')
    op.create_unique_constraint('uq_netsuite_code', 'netsuite_codes', ['netsuite_code'])
    
    # Add netsuite_name column
    op.add_column('netsuite_codes', sa.Column('netsuite_name', sa.String(length=255), nullable=True))
    
    # Add customer_id column with foreign key
    op.add_column('netsuite_codes', sa.Column('customer_id', sa.Integer(), nullable=True))
    op.create_foreign_key('netsuite_codes_customer_id_fkey', 'netsuite_codes', 'channel_customers', ['customer_id'], ['id'])


def downgrade() -> None:
    # Remove customer_id and netsuite_name from netsuite_codes
    op.drop_constraint('netsuite_codes_customer_id_fkey', 'netsuite_codes', type_='foreignkey')
    op.drop_column('netsuite_codes', 'customer_id')
    op.drop_column('netsuite_codes', 'netsuite_name')
    
    # Rename unique constraint back
    op.drop_constraint('uq_netsuite_code', 'netsuite_codes', type_='unique')
    op.create_unique_constraint('uq_retailer_code', 'netsuite_codes', ['retailer_code'])
    
    # Rename index back
    op.drop_index('idx_netsuite_code', table_name='netsuite_codes')
    op.create_index('idx_retailer_code', 'netsuite_codes', ['retailer_code'], unique=False)
    
    # Rename column back
    op.alter_column('netsuite_codes', 'netsuite_code', new_column_name='retailer_code')
    
    # Rename sequence back
    op.execute("ALTER SEQUENCE netsuite_codes_id_seq RENAME TO retailer_codes_id_seq")
    
    # Rename table back
    op.rename_table('netsuite_codes', 'retailer_codes')
    
    # Add back import fields to channel_customers
    op.add_column('channel_customers', sa.Column('import_code', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('channel_customers', sa.Column('import_name', sa.VARCHAR(length=255), autoincrement=False, nullable=True))

