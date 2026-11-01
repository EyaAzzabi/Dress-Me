"""add recommendation feedback

Revision ID: ab73d9e1c540
Revises: f7a2c19d4e6b
Create Date: 2026-10-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ab73d9e1c540"
down_revision: Union[str, Sequence[str], None] = "f7a2c19d4e6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendation_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("outfit_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.String(length=16), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rating IN ('like', 'dislike', 'worn')",
            name="ck_recommendation_feedback_rating",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["outfit_id"], ["outfits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outfit_id", name="uq_recommendation_feedback_outfit"),
    )
    op.create_index(
        "ix_recommendation_feedback_owner_id", "recommendation_feedback", ["owner_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_recommendation_feedback_owner_id", table_name="recommendation_feedback")
    op.drop_table("recommendation_feedback")
