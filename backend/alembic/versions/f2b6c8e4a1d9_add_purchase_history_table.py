"""add purchase_history table

Revision ID: f2b6c8e4a1d9
Revises: e5a9d1c7b2f8
Create Date: 2026-10-10 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f2b6c8e4a1d9'
down_revision: Union[str, Sequence[str], None] = 'e5a9d1c7b2f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'purchase_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('image_url', sa.String(length=1024), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('color', sa.String(length=50), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('verdict', sa.String(length=32), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('result', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_purchase_history_owner_id', 'purchase_history', ['owner_id'])
    op.create_index('ix_purchase_history_created_at', 'purchase_history', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_purchase_history_created_at', table_name='purchase_history')
    op.drop_index('ix_purchase_history_owner_id', table_name='purchase_history')
    op.drop_table('purchase_history')
