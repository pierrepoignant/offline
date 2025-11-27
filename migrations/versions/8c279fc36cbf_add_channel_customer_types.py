"""add_channel_customer_types

Revision ID: 8c279fc36cbf
Revises: 0a7f4bbaa7ba
Create Date: 2025-11-26 21:51:42.675474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c279fc36cbf'
down_revision: Union[str, None] = '0a7f4bbaa7ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create channel_customer_types table
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    if 'channel_customer_types' not in tables:
        op.create_table('channel_customer_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_channel_customer_type_name')
        )
    
    # Add customer_type_id to channel_customers table
    columns = [col['name'] for col in inspector.get_columns('channel_customers')]
    if 'customer_type_id' not in columns:
        op.add_column('channel_customers',
        sa.Column('customer_type_id', sa.Integer(), nullable=True)
        )
        op.create_foreign_key('fk_channel_customers_customer_type', 'channel_customers', 'channel_customer_types', ['customer_type_id'], ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # Remove customer_type_id from channel_customers
    op.drop_constraint('fk_channel_customers_customer_type', 'channel_customers', type_='foreignkey')
    op.drop_column('channel_customers', 'customer_type_id')
    
    # Drop channel_customer_types table
    op.drop_table('channel_customer_types')
    # ### end Alembic commands ###

