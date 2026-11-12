import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_sequence_migration_starts_after_existing_order_and_receipt_numbers() -> None:
    engine = create_engine("sqlite://")
    migration = importlib.import_module(
        "migrations.versions.0014_atomic_sequences"
    )

    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE work_orders (number VARCHAR(20) PRIMARY KEY)")
        )
        connection.execute(
            text("CREATE TABLE payments (receipt_number VARCHAR(20) PRIMARY KEY)")
        )
        connection.execute(
            text("INSERT INTO work_orders (number) VALUES ('OT-000007')")
        )
        connection.execute(
            text("INSERT INTO payments (receipt_number) VALUES ('CMP-000002')")
        )
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        counters = dict(
            connection.execute(
                text("SELECT name, next_value FROM sequence_counters")
            ).all()
        )

    assert counters == {"work-order": 8, "payment": 3}
    engine.dispose()
