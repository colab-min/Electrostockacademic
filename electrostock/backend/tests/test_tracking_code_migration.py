import hashlib
import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_tracking_code_migration_hashes_existing_codes() -> None:
    engine = create_engine("sqlite://")
    expected_hash = hashlib.sha256(b"K7M2QX9P4T").hexdigest()
    migration = importlib.import_module(
        "migrations.versions.0004_hash_tracking_codes"
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE work_orders ("
                "id VARCHAR(36) PRIMARY KEY, tracking_code VARCHAR(20) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX ix_work_orders_tracking_code "
                "ON work_orders (tracking_code)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO work_orders (id, tracking_code) "
                "VALUES ('order-1', 'K7M2QX9P4T')"
            )
        )
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        columns = {column["name"] for column in inspect(connection).get_columns("work_orders")}
        row = connection.execute(
            text("SELECT tracking_code_hash FROM work_orders WHERE id = 'order-1'")
        ).one()

    assert "tracking_code" not in columns
    assert row.tracking_code_hash == expected_hash
    engine.dispose()
