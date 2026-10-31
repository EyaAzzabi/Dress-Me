"""add season_source and attribute_confidence to clothing_items

Revision ID: a3c91e5b7d20
Revises: d84194b826a1
Create Date: 2026-10-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3c91e5b7d20'
down_revision: Union[str, Sequence[str], None] = 'd84194b826a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('clothing_items', sa.Column('season_source', sa.String(length=20), nullable=True))
    op.add_column('clothing_items', sa.Column('attribute_confidence', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('clothing_items', 'attribute_confidence')
    op.drop_column('clothing_items', 'season_source')
