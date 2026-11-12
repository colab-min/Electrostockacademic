"""Persist walk-in priorities and scheduled work-order capacity.

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "work_orders" in inspect(bind).get_table_names():
        columns = {
            column["name"] for column in inspect(bind).get_columns("work_orders")
        }
        additions = (
            sa.Column(
                "fault_type",
                sa.String(length=10),
                nullable=False,
                server_default="F03",
            ),
            sa.Column(
                "fault_priority",
                sa.String(length=10),
                nullable=False,
                server_default="MEDIUM",
            ),
            sa.Column(
                "estimated_duration_minutes",
                sa.Integer(),
                nullable=False,
                server_default="60",
            ),
            sa.Column("scheduled_start_at", sa.DateTime(timezone=True)),
        )
        for column in additions:
            if column.name not in columns:
                op.add_column("work_orders", column)

    tables = set(inspect(bind).get_table_names())
    if "work_order_slots" not in tables:
        op.create_table(
            "work_order_slots",
            sa.Column("work_order_id", sa.String(length=36), nullable=False),
            sa.Column("slot_id", sa.String(length=36), nullable=False),
            sa.ForeignKeyConstraint(
                ["work_order_id"],
                ["work_orders.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["slot_id"], ["slots.id"]),
            sa.PrimaryKeyConstraint("work_order_id", "slot_id"),
        )
    indexes = inspect(bind).get_indexes("work_order_slots")
    if not any(index.get("column_names") == ["slot_id"] for index in indexes):
        op.create_index(
            "ix_work_order_slots_slot_id",
            "work_order_slots",
            ["slot_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "work_order_slots" in tables:
        indexes = inspect(bind).get_indexes("work_order_slots")
        if any(index.get("column_names") == ["slot_id"] for index in indexes):
            op.drop_index("ix_work_order_slots_slot_id", table_name="work_order_slots")
        op.drop_table("work_order_slots")
    if "work_orders" in tables:
        columns = {
            column["name"] for column in inspect(bind).get_columns("work_orders")
        }
        for column_name in (
            "scheduled_start_at",
            "estimated_duration_minutes",
            "fault_priority",
            "fault_type",
        ):
            if column_name in columns:
                op.drop_column("work_orders", column_name)
