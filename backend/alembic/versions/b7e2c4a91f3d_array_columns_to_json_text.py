"""array columns to json text

Revision ID: b7e2c4a91f3d
Revises: d84194b826a1
Create Date: 2026-10-10 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e2c4a91f3d'
down_revision: Union[str, Sequence[str], None] = 'd84194b826a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The models store these lists as JSON text (JSONList / JSONUUIDList), not native
# Postgres arrays — the columns must match or every INSERT fails with DatatypeMismatch.
COLUMNS = [
    ('clothing_items', 'colors', 'varchar'),
    ('outfits', 'item_ids', 'uuid'),
    ('scheduled_outfits', 'item_ids', 'uuid'),
    ('packing_lists', 'item_ids', 'uuid'),
    ('packing_lists', 'checked_item_ids', 'uuid'),
]


def upgrade() -> None:
    """Upgrade schema."""
    for table, column, _ in COLUMNS:
        op.execute(f'ALTER TABLE {table} ALTER COLUMN {column} TYPE TEXT USING to_json({column})::text')


def downgrade() -> None:
    """Downgrade schema."""
    # ALTER ... USING can't contain a subquery, hence the temporary helper functions.
    op.execute("""
        CREATE FUNCTION pg_temp.json_text_to_varchar_array(t text) RETURNS varchar[]
        LANGUAGE sql IMMUTABLE AS $$ SELECT ARRAY(SELECT json_array_elements_text(t::json))::varchar[] $$
    """)
    op.execute("""
        CREATE FUNCTION pg_temp.json_text_to_uuid_array(t text) RETURNS uuid[]
        LANGUAGE sql IMMUTABLE AS $$ SELECT ARRAY(SELECT json_array_elements_text(t::json))::uuid[] $$
    """)
    for table, column, element_type in COLUMNS:
        op.execute(
            f'ALTER TABLE {table} ALTER COLUMN {column} TYPE {element_type}[] '
            f'USING pg_temp.json_text_to_{element_type}_array({column})'
        )
