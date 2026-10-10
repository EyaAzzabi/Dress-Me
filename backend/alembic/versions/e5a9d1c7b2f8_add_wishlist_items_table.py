"""add wishlist_items table

Revision ID: e5a9d1c7b2f8
Revises: c3f1a8d2e6b4
Create Date: 2026-10-10 21:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5a9d1c7b2f8'
down_revision: Union[str, Sequence[str], None] = 'c3f1a8d2e6b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wishlist_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('item_key', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=512), nullable=False),
        sa.Column('brand', sa.String(length=128), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('image_url', sa.String(length=1024), nullable=True),
        sa.Column('saved_price', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_id', 'item_key'),
    )
    op.create_index('ix_wishlist_items_owner_id', 'wishlist_items', ['owner_id'])


def downgrade() -> None:
    op.drop_index('ix_wishlist_items_owner_id', table_name='wishlist_items')
    op.drop_table('wishlist_items')
