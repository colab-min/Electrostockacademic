"""Add failed-login lockout and refresh-session families.

Revision ID: 0010
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "0010"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        user_columns = {
            column["name"] for column in inspector.get_columns("users")
        }
        if "failed_login_attempts" not in user_columns:
            op.add_column(
                "users",
                sa.Column(
                    "failed_login_attempts",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
            )
        if "failed_login_started_at" not in user_columns:
            op.add_column(
                "users",
                sa.Column("failed_login_started_at", sa.DateTime(timezone=True)),
            )
        if "login_locked_until" not in user_columns:
            op.add_column(
                "users",
                sa.Column("login_locked_until", sa.DateTime(timezone=True)),
            )

    if "refresh_sessions" not in tables:
        return

    refresh_columns = {
        column["name"]: column
        for column in inspect(bind).get_columns("refresh_sessions")
    }
    if "family_id" not in refresh_columns:
        op.add_column(
            "refresh_sessions",
            sa.Column("family_id", sa.String(length=36), nullable=True),
        )
        refresh_columns["family_id"] = {"nullable": True}

    if refresh_columns["family_id"]["nullable"]:
        bind.execute(
            text(
                "UPDATE refresh_sessions SET family_id = id "
                "WHERE family_id IS NULL"
            )
        )
        with op.batch_alter_table("refresh_sessions") as batch:
            batch.alter_column(
                "family_id",
                existing_type=sa.String(length=36),
                nullable=False,
            )

    indexes = inspect(bind).get_indexes("refresh_sessions")
    if not any(index.get("column_names") == ["family_id"] for index in indexes):
        op.create_index(
            "ix_refresh_sessions_family_id",
            "refresh_sessions",
            ["family_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "refresh_sessions" in tables:
        indexes = inspect(bind).get_indexes("refresh_sessions")
        if any(index.get("column_names") == ["family_id"] for index in indexes):
            op.drop_index("ix_refresh_sessions_family_id", table_name="refresh_sessions")
        if "family_id" in {
            column["name"] for column in inspect(bind).get_columns("refresh_sessions")
        }:
            op.drop_column("refresh_sessions", "family_id")

    if "users" in tables:
        user_columns = {
            column["name"] for column in inspect(bind).get_columns("users")
        }
        for column_name in (
            "login_locked_until",
            "failed_login_started_at",
            "failed_login_attempts",
        ):
            if column_name in user_columns:
                op.drop_column("users", column_name)
