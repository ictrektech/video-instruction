"""init user table

Revision ID: 57691f8aa452
Revises:
Create Date: 2026-06-11 10:45:56.810560
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "57691f8aa452"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_user",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password", sa.String(length=64), nullable=False),
        sa.Column("real_name", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("status", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_time", sa.DateTime(), nullable=True),
        sa.Column("update_time", sa.DateTime(), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sys_user_username"), "sys_user", ["username"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sys_user_username"), table_name="sys_user")
    op.drop_table("sys_user")
