"""add clothing_items.embedding

Revision ID: c3f1a8d2e6b4
Revises: b7e2c4a91f3d
Create Date: 2026-10-10 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3f1a8d2e6b4'
down_revision: Union[str, Sequence[str], None] = 'b7e2c4a91f3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('clothing_items', sa.Column('embedding', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('clothing_items', 'embedding')
