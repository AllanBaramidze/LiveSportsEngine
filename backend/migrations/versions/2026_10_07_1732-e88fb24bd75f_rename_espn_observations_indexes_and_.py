"""rename espn_observations indexes and constraints

Revision ID: e88fb24bd75f
Revises: fcb63c93311f
Create Date: 2026-10-07 17:32:21.349480

`rename_table` only renames the table itself; the sequence, index and constraints
keep their old `observations_` names. This renames them to match. No data changes.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e88fb24bd75f"
down_revision: str | Sequence[str] | None = "fcb63c93311f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (old name, new name)
SEQUENCE = ("observations_id_seq", "espn_observations_id_seq")
INDEX = ("ix_observations_espn_id_wall_clock", "ix_espn_observations_espn_id_wall_clock")
CONSTRAINTS = [
    ("observations_pkey", "espn_observations_pkey"),
    ("observations_espn_id_fkey", "espn_observations_espn_id_fkey"),
    (
        "observations_espn_id_play_id_espn_home_prob_espn_tie_prob_e_key",
        "uq_espn_observations_reading",
    ),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(f"ALTER SEQUENCE {SEQUENCE[0]} RENAME TO {SEQUENCE[1]}")
    op.execute(f"ALTER INDEX {INDEX[0]} RENAME TO {INDEX[1]}")
    for old, new in CONSTRAINTS:
        op.execute(f"ALTER TABLE espn_observations RENAME CONSTRAINT {old} TO {new}")


def downgrade() -> None:
    """Downgrade schema."""
    for old, new in CONSTRAINTS:
        op.execute(f"ALTER TABLE espn_observations RENAME CONSTRAINT {new} TO {old}")
    op.execute(f"ALTER INDEX {INDEX[1]} RENAME TO {INDEX[0]}")
    op.execute(f"ALTER SEQUENCE {SEQUENCE[1]} RENAME TO {SEQUENCE[0]}")
