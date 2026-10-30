"""add inventory price quantity and sizes"""

revision = "b31c7d9a2e44"
down_revision = "9a2c4d6e8f10"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column("clothing_items", sa.Column("price", sa.Float(), nullable=True))
    op.add_column("clothing_items", sa.Column("quantity", sa.Integer(), server_default="1", nullable=False))
    op.add_column("clothing_items", sa.Column("sizes", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("clothing_items", "sizes")
    op.drop_column("clothing_items", "quantity")
    op.drop_column("clothing_items", "price")
