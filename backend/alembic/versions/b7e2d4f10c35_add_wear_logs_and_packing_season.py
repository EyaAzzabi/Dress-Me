"""add wear_logs table and packing_lists start_date/season

Revision ID: b7e2d4f10c35
Revises: a3c91e5b7d20
Create Date: 2026-10-10 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7e2d4f10c35'
down_revision: Union[str, Sequence[str], None] = 'a3c91e5b7d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('wear_logs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['clothing_items.id'], ),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('item_id', 'date', name='uq_wear_log_item_date')
    )
    op.add_column('packing_lists', sa.Column('start_date', sa.Date(), nullable=True))
    op.add_column('packing_lists', sa.Column('season', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('packing_lists', 'season')
    op.drop_column('packing_lists', 'start_date')
    op.drop_table('wear_logs')
