"""add user roles and stylist recommendations

Revision ID: 9a2c4d6e8f10
Revises: ad320eb7f100
"""
from alembic import op
import sqlalchemy as sa

revision = "9a2c4d6e8f10"
down_revision = "ad320eb7f100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(length=50), server_default="customer", nullable=False))
    op.create_table(
        "stylist_recommendations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("stylist_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("item_ids", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["stylist_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stylist_recommendations_stylist_id", "stylist_recommendations", ["stylist_id"])
    op.create_index("ix_stylist_recommendations_customer_id", "stylist_recommendations", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_stylist_recommendations_customer_id", table_name="stylist_recommendations")
    op.drop_index("ix_stylist_recommendations_stylist_id", table_name="stylist_recommendations")
    op.drop_table("stylist_recommendations")
    op.drop_column("users", "role")
