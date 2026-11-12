"""Motor y sesión de SQLAlchemy (MySQL 8.4)."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DB_URL

engine = create_engine(DB_URL, pool_pre_ping=True, isolation_level="READ COMMITTED")
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
