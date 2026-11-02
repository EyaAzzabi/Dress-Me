"""add rlhf feedback table

Revision ID: a1b2c3d4e5f6
Revises: ab73d9e1c540
Create Date: 2026-11-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "ab73d9e1c540"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rlhf_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("outfit_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("items_liked", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("items_disliked", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("occasion_matched", sa.Boolean(), nullable=True),
        sa.Column("seasonal_appropriate", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_rlhf_feedback_rating"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["outfit_id"], ["outfits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_rlhf_user_created", "rlhf_feedback", ["user_id", "created_at"], unique=False)
    op.create_index("idx_rlhf_outfit_rating", "rlhf_feedback", ["outfit_id", "rating"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_rlhf_outfit_rating", table_name="rlhf_feedback")
    op.drop_index("idx_rlhf_user_created", table_name="rlhf_feedback")
    op.drop_table("rlhf_feedback")
