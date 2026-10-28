"""rename observations to espn_observations

Revision ID: fcb63c93311f
Revises: 139287d509ae
Create Date: 2026-10-07 17:26:37.847331

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fcb63c93311f"
down_revision: str | Sequence[str] | None = "139287d509ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table("observations", "espn_observations")

def downgrade() -> None:
    """Downgrade schema."""
    op.rename_table("espn_observations", "observations")