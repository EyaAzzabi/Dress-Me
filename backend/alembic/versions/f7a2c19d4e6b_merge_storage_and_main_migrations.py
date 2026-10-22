"""merge the local list-storage migration with the main migration chain

Revision ID: f7a2c19d4e6b
Revises: c4a17e92b53d, f2b6c8e4a1d9
Create Date: 2026-10-11

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "f7a2c19d4e6b"
down_revision: Union[str, Sequence[str], None] = ("c4a17e92b53d", "f2b6c8e4a1d9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
