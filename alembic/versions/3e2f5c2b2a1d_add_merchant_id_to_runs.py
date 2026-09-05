"""add merchant_id to runs

Revision ID: 3e2f5c2b2a1d
Revises: 71bc304d90f7
Create Date: 2026-08-28 22:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3e2f5c2b2a1d"
down_revision: Union[str, None] = "71bc304d90f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("merchant_id", sa.Text(), nullable=False, server_default="demo_merchant"))
    op.create_index("ix_runs_merchant_id", "runs", ["merchant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_runs_merchant_id", table_name="runs")
    op.drop_column("runs", "merchant_id")
