"""Add reservation expiry, queue position, and notification delivery data.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from app.database import Base
from app import models  # noqa: F401

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    inspector = inspect(op.get_bind())
    if table in inspector.get_table_names():
        existing = {item["name"] for item in inspector.get_columns(table)}
        if column.name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    _add_column_if_missing(
        "appointments",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        "work_orders",
        sa.Column("queue_position", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        "notifications",
        sa.Column("appointment_id", sa.String(length=36), nullable=True),
    )
    _add_column_if_missing(
        "notifications",
        sa.Column("work_order_id", sa.String(length=36), nullable=True),
    )
    _add_column_if_missing(
        "notifications",
        sa.Column("payload", sa.JSON(), nullable=True),
    )
    _add_column_if_missing(
        "notifications",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_column_if_missing(
        "notifications",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    for table, column in (
        ("notifications", "next_attempt_at"),
        ("notifications", "attempts"),
        ("notifications", "payload"),
        ("notifications", "work_order_id"),
        ("notifications", "appointment_id"),
        ("work_orders", "queue_position"),
        ("appointments", "expires_at"),
    ):
        if table in inspector.get_table_names():
            existing = {item["name"] for item in inspector.get_columns(table)}
            if column in existing:
                op.drop_column(table, column)
