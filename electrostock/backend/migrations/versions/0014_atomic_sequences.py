"""Initialize persistent counters for generated business numbers.

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _insert_counter(name: str, table: str, column: str, prefix: str) -> None:
    bind = op.get_bind()
    existing = bind.execute(
        text("SELECT next_value FROM sequence_counters WHERE name = :name"),
        {"name": name},
    ).scalar_one_or_none()
    maximum = 0
    for value in bind.execute(text(f"SELECT {column} FROM {table}")).scalars():
        if isinstance(value, str) and value.startswith(prefix):
            number = value.removeprefix(prefix)
            if number.isdigit():
                maximum = max(maximum, int(number))
    next_value = maximum + 1
    if existing is None:
        bind.execute(
            text(
                "INSERT INTO sequence_counters (name, next_value) "
                "VALUES (:name, :next_value)"
            ),
            {"name": name, "next_value": next_value},
        )
    elif existing < next_value:
        bind.execute(
            text(
                "UPDATE sequence_counters SET next_value = :next_value "
                "WHERE name = :name"
            ),
            {"name": name, "next_value": next_value},
        )


def upgrade() -> None:
    bind = op.get_bind()
    if "sequence_counters" not in inspect(bind).get_table_names():
        op.create_table(
            "sequence_counters",
            sa.Column("name", sa.String(length=40), nullable=False),
            sa.Column("next_value", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("name"),
        )
    _insert_counter("work-order", "work_orders", "number", "OT-")
    _insert_counter("payment", "payments", "receipt_number", "CMP-")


def downgrade() -> None:
    if "sequence_counters" in inspect(op.get_bind()).get_table_names():
        op.drop_table("sequence_counters")
