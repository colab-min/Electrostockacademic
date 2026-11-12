"""Preserve reserved parts for each appointment.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "appointment_part_reservations" not in inspect(bind).get_table_names():
        op.create_table(
            "appointment_part_reservations",
            sa.Column("appointment_id", sa.String(length=36), nullable=False),
            sa.Column("part_id", sa.String(length=36), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.CheckConstraint(
                "quantity > 0",
                name="ck_appointment_part_quantity_positive",
            ),
            sa.ForeignKeyConstraint(
                ["appointment_id"],
                ["appointments.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["part_id"], ["parts.id"]),
            sa.PrimaryKeyConstraint("appointment_id", "part_id"),
        )
    indexes = inspect(bind).get_indexes("appointment_part_reservations")
    if not any(index.get("column_names") == ["part_id"] for index in indexes):
        op.create_index(
            "ix_appointment_part_reservations_part_id",
            "appointment_part_reservations",
            ["part_id"],
        )

    bind.execute(
        text(
            "INSERT INTO appointment_part_reservations "
            "(appointment_id, part_id, quantity) "
            "SELECT appointments.id, service_parts.part_id, service_parts.quantity "
            "FROM appointments "
            "JOIN service_parts ON service_parts.service_id = appointments.service_id "
            "WHERE appointments.status IN ('HELD', 'CONFIRMED', 'RESCHEDULED') "
            "AND NOT EXISTS ("
            "SELECT 1 FROM appointment_part_reservations "
            "WHERE appointment_part_reservations.appointment_id = appointments.id "
            "AND appointment_part_reservations.part_id = service_parts.part_id"
            ")"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "appointment_part_reservations" not in inspect(bind).get_table_names():
        return
    indexes = inspect(bind).get_indexes("appointment_part_reservations")
    if any(index.get("column_names") == ["part_id"] for index in indexes):
        op.drop_index(
            "ix_appointment_part_reservations_part_id",
            table_name="appointment_part_reservations",
        )
    op.drop_table("appointment_part_reservations")
