"""Require notification payload and relate notifications to entities.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "notifications" not in inspector.get_table_names():
        return
    columns = {item["name"]: item for item in inspector.get_columns("notifications")}
    foreign_keys = inspector.get_foreign_keys("notifications")

    with op.batch_alter_table("notifications") as batch:
        if columns.get("payload", {}).get("nullable", False):
            batch.execute(sa.text("UPDATE notifications SET payload = '{}' WHERE payload IS NULL"))
            batch.alter_column(
                "payload",
                existing_type=sa.JSON(),
                nullable=False,
            )
        if not any(item.get("constrained_columns") == ["appointment_id"] for item in foreign_keys):
            batch.create_foreign_key(
                "fk_notifications_appointment",
                "appointments",
                ["appointment_id"],
                ["id"],
            )
        if not any(item.get("constrained_columns") == ["work_order_id"] for item in foreign_keys):
            batch.create_foreign_key(
                "fk_notifications_work_order",
                "work_orders",
                ["work_order_id"],
                ["id"],
            )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "notifications" not in inspector.get_table_names():
        return
    foreign_keys = inspector.get_foreign_keys("notifications")
    with op.batch_alter_table("notifications") as batch:
        if any(item.get("name") == "fk_notifications_work_order" for item in foreign_keys):
            batch.drop_constraint("fk_notifications_work_order", type_="foreignkey")
        if any(item.get("name") == "fk_notifications_appointment" for item in foreign_keys):
            batch.drop_constraint("fk_notifications_appointment", type_="foreignkey")
