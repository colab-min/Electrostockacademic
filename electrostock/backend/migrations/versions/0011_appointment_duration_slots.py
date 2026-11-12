"""Reserve every consecutive slot required by an appointment.

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "appointment_slots" not in inspect(op.get_bind()).get_table_names():
        op.create_table(
            "appointment_slots",
            sa.Column("appointment_id", sa.String(length=36), nullable=False),
            sa.Column("slot_id", sa.String(length=36), nullable=False),
            sa.ForeignKeyConstraint(
                ["appointment_id"],
                ["appointments.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["slot_id"], ["slots.id"]),
            sa.PrimaryKeyConstraint("appointment_id", "slot_id"),
        )
    indexes = inspect(op.get_bind()).get_indexes("appointment_slots")
    if not any(index.get("column_names") == ["slot_id"] for index in indexes):
        op.create_index(
            "ix_appointment_slots_slot_id",
            "appointment_slots",
            ["slot_id"],
        )
    op.get_bind().execute(
        text(
            "INSERT INTO appointment_slots (appointment_id, slot_id) "
            "SELECT appointments.id, appointments.slot_id FROM appointments "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM appointment_slots "
            "WHERE appointment_slots.appointment_id = appointments.id "
            "AND appointment_slots.slot_id = appointments.slot_id"
            ")"
        )
    )


def downgrade() -> None:
    if "appointment_slots" in inspect(op.get_bind()).get_table_names():
        indexes = inspect(op.get_bind()).get_indexes("appointment_slots")
        if any(index.get("column_names") == ["slot_id"] for index in indexes):
            op.drop_index(
                "ix_appointment_slots_slot_id",
                table_name="appointment_slots",
            )
        op.drop_table("appointment_slots")
