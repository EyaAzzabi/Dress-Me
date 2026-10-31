"""store model list columns as JSON text

Revision ID: c4a17e92b53d
Revises: d84194b826a1
Create Date: 2026-10-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4a17e92b53d"
down_revision: Union[str, Sequence[str], None] = "d84194b826a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LIST_COLUMNS = [
    ("clothing_items", "colors", postgresql.ARRAY(sa.String())),
    ("outfits", "item_ids", postgresql.ARRAY(sa.UUID())),
    ("scheduled_outfits", "item_ids", postgresql.ARRAY(sa.UUID())),
    ("packing_lists", "item_ids", postgresql.ARRAY(sa.UUID())),
    ("packing_lists", "checked_item_ids", postgresql.ARRAY(sa.UUID())),
]


def _column_type(table: str, column: str):
    return next(
        item["type"]
        for item in sa.inspect(op.get_bind()).get_columns(table)
        if item["name"] == column
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column, array_type in LIST_COLUMNS:
        if not isinstance(_column_type(table, column), postgresql.ARRAY):
            continue
        op.alter_column(
            table,
            column,
            existing_type=array_type,
            type_=sa.Text(),
            postgresql_using=f"to_json({column})::text",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "CREATE FUNCTION pg_temp.json_text_to_array(t text) RETURNS text[] AS "
        "$$ SELECT CASE WHEN t IS NULL THEN NULL "
        "ELSE ARRAY(SELECT json_array_elements_text(t::json)) END $$ LANGUAGE sql IMMUTABLE"
    )
    for table, column, array_type in LIST_COLUMNS:
        if not isinstance(_column_type(table, column), sa.Text):
            continue
        op.alter_column(
            table,
            column,
            existing_type=sa.Text(),
            type_=array_type,
            postgresql_using=f"pg_temp.json_text_to_array({column})::{array_type}",
        )
