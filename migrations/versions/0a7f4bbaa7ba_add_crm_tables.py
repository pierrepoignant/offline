"""add_crm_tables

Revision ID: 0a7f4bbaa7ba
Revises: a1b2c3d4e5f6
Create Date: 2025-11-26 21:36:44.555671

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a7f4bbaa7ba'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ticket_status enum type (if it doesn't exist)
    from sqlalchemy import inspect, text
    bind = op.get_bind()
    inspector = inspect(bind)
    
    # Create enum type using DO block to handle if it already exists
    op.execute(text("""
        DO $$ BEGIN
            CREATE TYPE ticket_status AS ENUM ('opened', 'closed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))
    
    tables = inspector.get_table_names()
    
    # Create crm_ticket_types table
    if 'crm_ticket_types' not in tables:
        op.create_table('crm_ticket_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_crm_ticket_type_name')
        )
    
    # Create crm_tickets table
    if 'crm_tickets' not in tables:
        op.create_table('crm_tickets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('ticket_type_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('opened', 'closed', name='ticket_status', native_enum=False, create_type=False), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('creator_id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['channel_customers.id'], ),
        sa.ForeignKeyConstraint(['ticket_type_id'], ['crm_ticket_types.id'], ),
        sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index('idx_crm_ticket_customer', 'crm_tickets', ['customer_id'], unique=False)
        op.create_index('idx_crm_ticket_status', 'crm_tickets', ['status'], unique=False)
        op.create_index('idx_crm_ticket_due_date', 'crm_tickets', ['due_date'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # Drop crm_tickets table
    op.drop_index('idx_crm_ticket_due_date', table_name='crm_tickets')
    op.drop_index('idx_crm_ticket_status', table_name='crm_tickets')
    op.drop_index('idx_crm_ticket_customer', table_name='crm_tickets')
    op.drop_table('crm_tickets')
    
    # Drop crm_ticket_types table
    op.drop_table('crm_ticket_types')
    
    # Drop ticket_status enum type
    op.execute("DROP TYPE IF EXISTS ticket_status")
    # ### end Alembic commands ###

