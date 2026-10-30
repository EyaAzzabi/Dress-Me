"""add boutique orders

Revision ID: c93e7a5b1d42
Revises: b31c7d9a2e44
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c93e7a5b1d42"
down_revision: Union[str, Sequence[str], None] = "b31c7d9a2e44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "boutique_orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("stylist_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("size", sa.String(length=20), nullable=True),
        sa.Column("customer_phone", sa.String(length=30), nullable=True),
        sa.Column("delivery_address", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stylist_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["clothing_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("boutique_orders")
