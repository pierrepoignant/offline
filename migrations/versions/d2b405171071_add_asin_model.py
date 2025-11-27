"""add_asin_model

Revision ID: a1b2c3d4e5f8
Revises: 7c1f31866804
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2b405171071'
down_revision: Union[str, None] = '7c1f31866804'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create asins table
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    if 'asins' not in tables:
        op.create_table('asins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asin', sa.String(length=255), nullable=False),
        sa.Column('img_url', sa.String(length=512), nullable=True),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('scraped_at', sa.Date(), nullable=True),
        sa.Column('scraped_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asin', name='uq_asin_asin')
        )
        op.create_index('idx_asin_asin', 'asins', ['asin'], unique=False)
    
    # Add asin_id to items table and remove old asin/img_url columns
    if 'asin_id' not in [col['name'] for col in inspector.get_columns('items')]:
        # First, add the new asin_id column
        op.add_column('items', sa.Column('asin_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_items_asin_id', 'items', 'asins', ['asin_id'], ['id'])
        op.create_index('idx_items_asin_id', 'items', ['asin_id'], unique=False)
        
        # Migrate existing asin data if any
        # Note: This assumes asin values exist and need to be migrated
        # We'll create ASIN records for existing asin values
        connection = op.get_bind()
        result = connection.execute(sa.text("SELECT DISTINCT asin FROM items WHERE asin IS NOT NULL AND asin != ''"))
        existing_asins = result.fetchall()
        
        for (asin_value,) in existing_asins:
            # Check if ASIN already exists
            asin_check = connection.execute(
                sa.text("SELECT id FROM asins WHERE asin = :asin"),
                {'asin': asin_value}
            ).fetchone()
            
            if not asin_check:
                # Create ASIN record
                connection.execute(
                    sa.text("INSERT INTO asins (asin, created_at) VALUES (:asin, NOW())"),
                    {'asin': asin_value}
                )
            
            # Update items with asin_id
            asin_id = connection.execute(
                sa.text("SELECT id FROM asins WHERE asin = :asin"),
                {'asin': asin_value}
            ).fetchone()[0]
            
            connection.execute(
                sa.text("UPDATE items SET asin_id = :asin_id WHERE asin = :asin"),
                {'asin_id': asin_id, 'asin': asin_value}
            )
        
        # Remove old columns
        op.drop_column('items', 'asin')
        op.drop_column('items', 'img_url')
    # ### end Alembic commands ###


def downgrade() -> None:
    # Add back old columns to items
    op.add_column('items', sa.Column('asin', sa.String(length=255), nullable=True))
    op.add_column('items', sa.Column('img_url', sa.String(length=512), nullable=True))
    
    # Migrate data back
    connection = op.get_bind()
    result = connection.execute(sa.text("SELECT id, asin_id FROM items WHERE asin_id IS NOT NULL"))
    items_with_asin = result.fetchall()
    
    for item_id, asin_id in items_with_asin:
        asin_result = connection.execute(
            sa.text("SELECT asin, img_url FROM asins WHERE id = :asin_id"),
            {'asin_id': asin_id}
        ).fetchone()
        
        if asin_result:
            asin_value, img_url_value = asin_result
            connection.execute(
                sa.text("UPDATE items SET asin = :asin, img_url = :img_url WHERE id = :item_id"),
                {'asin': asin_value, 'img_url': img_url_value, 'item_id': item_id}
            )
    
    # Remove foreign key and column
    op.drop_constraint('fk_items_asin_id', 'items', type_='foreignkey')
    op.drop_index('idx_items_asin_id', table_name='items')
    op.drop_column('items', 'asin_id')
    
    # Drop asins table
    op.drop_index('idx_asin_asin', table_name='asins')
    op.drop_table('asins')
    # ### end Alembic commands ###

