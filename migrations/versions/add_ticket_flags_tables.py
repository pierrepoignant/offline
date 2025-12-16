"""add_ticket_flags_tables

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2025-01-27 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    # Create crm_ticket_flags table
    if 'crm_ticket_flags' not in tables:
        op.create_table('crm_ticket_flags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_crm_ticket_flag_name')
        )
    
    # Create crm_tickets_x_flags junction table
    if 'crm_tickets_x_flags' not in tables:
        op.create_table('crm_tickets_x_flags',
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('flag_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['crm_tickets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['flag_id'], ['crm_ticket_flags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('ticket_id', 'flag_id')
        )
        op.create_index('idx_ticket_flag_ticket', 'crm_tickets_x_flags', ['ticket_id'], unique=False)
        op.create_index('idx_ticket_flag_flag', 'crm_tickets_x_flags', ['flag_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # Drop crm_tickets_x_flags table
    op.drop_index('idx_ticket_flag_flag', table_name='crm_tickets_x_flags')
    op.drop_index('idx_ticket_flag_ticket', table_name='crm_tickets_x_flags')
    op.drop_table('crm_tickets_x_flags')
    
    # Drop crm_ticket_flags table
    op.drop_table('crm_ticket_flags')
    # ### end Alembic commands ###

