"""Persist walk-in idempotency keys.

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "idempotency_records" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "idempotency_records",
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resource_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("scope", "key"),
    )


def downgrade() -> None:
    if "idempotency_records" in inspect(op.get_bind()).get_table_names():
        op.drop_table("idempotency_records")
