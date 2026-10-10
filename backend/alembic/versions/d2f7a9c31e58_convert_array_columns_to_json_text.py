"""convert Postgres array columns to the JSON text the models now use

The models store lists as JSON strings (JSONList / JSONUUIDList, portable across
databases), but the earlier migrations created native Postgres arrays. With a database
built from those migrations the ORM can neither read nor write these columns. This
converts them in place, keeping the data; downgrade converts back.

Revision ID: d2f7a9c31e58
Revises: c4d8f1a6b392
Create Date: 2026-10-10 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd2f7a9c31e58'
down_revision: Union[str, Sequence[str], None] = 'c4d8f1a6b392'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column, native array type, default-less?)
COLUMNS = [
    ("clothing_items", "colors", "varchar[]"),
    ("outfits", "item_ids", "uuid[]"),
    ("scheduled_outfits", "item_ids", "uuid[]"),
    ("packing_lists", "item_ids", "uuid[]"),
    ("packing_lists", "checked_item_ids", "uuid[]"),
]


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return  # other databases never had native arrays
    for table, column, _ in COLUMNS:
        # to_json(NULL) is NULL, and to_json(uuid[]) gives ["…","…"] — exactly what the
        # models' JSON type decorators read back.
        op.execute(f'ALTER TABLE {table} ALTER COLUMN {column} TYPE text USING to_json({column})::text')


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    # ALTER ... USING can't contain a subquery, so the JSON -> array step lives in a
    # throwaway function.
    op.execute(
        "CREATE FUNCTION pg_temp.json_text_to_array(t text) RETURNS text[] AS "
        "$$ SELECT CASE WHEN t IS NULL THEN NULL "
        "ELSE ARRAY(SELECT json_array_elements_text(t::json)) END $$ LANGUAGE sql IMMUTABLE"
    )
    for table, column, array_type in COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {array_type} "
            f"USING pg_temp.json_text_to_array({column})::{array_type}"
        )
