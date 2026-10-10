"""add render_image_url and render_signature to scheduled_outfits

Revision ID: c4d8f1a6b392
Revises: b7e2d4f10c35
Create Date: 2026-10-10 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4d8f1a6b392'
down_revision: Union[str, Sequence[str], None] = 'b7e2d4f10c35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('scheduled_outfits', sa.Column('render_image_url', sa.String(length=1024), nullable=True))
    op.add_column('scheduled_outfits', sa.Column('render_signature', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('scheduled_outfits', 'render_signature')
    op.drop_column('scheduled_outfits', 'render_image_url')
