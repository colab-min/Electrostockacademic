"""Store work-order tracking codes as SHA-256 digests.

Revision ID: 0004
Revises: 0003
"""
import hashlib

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _hash_tracking_code(code: str) -> str:
    return hashlib.sha256(code.upper().encode("ascii")).hexdigest()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "work_orders" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("work_orders")}
    if "tracking_code" not in columns:
        return
    if "tracking_code_hash" not in columns:
        op.add_column(
            "work_orders",
            sa.Column("tracking_code_hash", sa.String(length=64), nullable=True),
        )

    rows = bind.execute(
        text(
            "SELECT id, tracking_code FROM work_orders "
            "WHERE tracking_code_hash IS NULL"
        )
    ).all()
    for order_id, tracking_code in rows:
        bind.execute(
            text(
                "UPDATE work_orders SET tracking_code_hash = :code_hash "
                "WHERE id = :order_id"
            ),
            {
                "code_hash": _hash_tracking_code(tracking_code),
                "order_id": order_id,
            },
        )

    indexes = inspect(bind).get_indexes("work_orders")
    old_indexes = [
        index["name"]
        for index in indexes
        if index.get("column_names") == ["tracking_code"]
    ]
    has_hash_index = any(
        index.get("column_names") == ["tracking_code_hash"] for index in indexes
    )
    with op.batch_alter_table("work_orders") as batch:
        batch.alter_column(
            "tracking_code_hash",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        for index_name in old_indexes:
            batch.drop_index(index_name)
        batch.drop_column("tracking_code")
        if not has_hash_index:
            batch.create_index(
                "ix_work_orders_tracking_code_hash",
                ["tracking_code_hash"],
                unique=True,
            )


def downgrade() -> None:
    raise RuntimeError("Tracking codes are hashed and cannot be restored from the database.")
