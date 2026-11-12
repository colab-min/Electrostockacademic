import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_appointment_part_migration_snapshots_active_reservations() -> None:
    engine = create_engine("sqlite://")
    migration = importlib.import_module(
        "migrations.versions.0012_appointment_part_snapshots"
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE appointments ("
                "id VARCHAR(36) PRIMARY KEY, service_id VARCHAR(36), "
                "status VARCHAR(20))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE parts (id VARCHAR(36) PRIMARY KEY)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE service_parts ("
                "service_id VARCHAR(36), part_id VARCHAR(36), quantity INTEGER)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO appointments (id, service_id, status) "
                "VALUES ('active-appointment', 'service-1', 'CONFIRMED'), "
                "('cancelled-appointment', 'service-1', 'CANCELLED')"
            )
        )
        connection.execute(text("INSERT INTO parts (id) VALUES ('part-1')"))
        connection.execute(
            text(
                "INSERT INTO service_parts (service_id, part_id, quantity) "
                "VALUES ('service-1', 'part-1', 2)"
            )
        )
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        rows = connection.execute(
            text(
                "SELECT appointment_id, part_id, quantity "
                "FROM appointment_part_reservations"
            )
        ).all()

    assert rows == [("active-appointment", "part-1", 2)]
    engine.dispose()
