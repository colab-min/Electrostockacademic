import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_appointment_slots_migration_backfills_existing_start_slots() -> None:
    engine = create_engine("sqlite://")
    migration = importlib.import_module(
        "migrations.versions.0011_appointment_duration_slots"
    )

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE slots (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE appointments ("
                "id VARCHAR(36) PRIMARY KEY, slot_id VARCHAR(36) NOT NULL)"
            )
        )
        connection.execute(text("INSERT INTO slots (id) VALUES ('slot-1')"))
        connection.execute(
            text(
                "INSERT INTO appointments (id, slot_id) "
                "VALUES ('appointment-1', 'slot-1')"
            )
        )
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        association = connection.execute(
            text(
                "SELECT appointment_id, slot_id FROM appointment_slots "
                "WHERE appointment_id = 'appointment-1'"
            )
        ).one()

    assert association == ("appointment-1", "slot-1")
    engine.dispose()
