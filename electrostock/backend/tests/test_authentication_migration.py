import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_authentication_migration_adds_lockout_and_backfills_refresh_families() -> None:
    engine = create_engine("sqlite://")
    migration = importlib.import_module(
        "migrations.versions.0010_authentication_hardening"
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users ("
                "id VARCHAR(36) PRIMARY KEY, email VARCHAR(160) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE refresh_sessions ("
                "id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL, "
                "token_id VARCHAR(36) NOT NULL, expires_at DATETIME NOT NULL, "
                "revoked BOOLEAN NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO refresh_sessions "
                "(id, user_id, token_id, expires_at, revoked) "
                "VALUES ('session-1', 'user-1', 'token-1', "
                "'2030-01-01 00:00:00', 0)"
            )
        )
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        user_columns = {
            column["name"] for column in inspect(connection).get_columns("users")
        }
        family_column = next(
            column
            for column in inspect(connection).get_columns("refresh_sessions")
            if column["name"] == "family_id"
        )
        family_id = connection.execute(
            text("SELECT family_id FROM refresh_sessions WHERE id = 'session-1'")
        ).scalar_one()

    assert {
        "failed_login_attempts",
        "failed_login_started_at",
        "login_locked_until",
    }.issubset(user_columns)
    assert family_column["nullable"] is False
    assert family_id == "session-1"
    engine.dispose()
