from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import SequenceCounter


def _next_value(values: list[str], prefix: str) -> int:
    numbers = [
        int(value.removeprefix(prefix))
        for value in values
        if value.startswith(prefix) and value.removeprefix(prefix).isdigit()
    ]
    return max(numbers, default=0) + 1


def next_sequence_value(
    db: Session,
    name: str,
    values_query: Select[tuple[str]],
    prefix: str,
) -> int:
    counter = db.scalar(
        select(SequenceCounter)
        .where(SequenceCounter.name == name)
        .with_for_update()
    )
    if counter is None:
        counter = SequenceCounter(
            name=name,
            next_value=_next_value(list(db.scalars(values_query)), prefix),
        )
        db.add(counter)
        db.flush()
    value = counter.next_value
    counter.next_value += 1
    return value


def synchronize_sequence(
    db: Session,
    name: str,
    values_query: Select[tuple[str]],
    prefix: str,
) -> None:
    required_next_value = _next_value(list(db.scalars(values_query)), prefix)
    counter = db.get(SequenceCounter, name)
    if counter is None:
        db.add(
            SequenceCounter(
                name=name,
                next_value=required_next_value,
            )
        )
    elif counter.next_value < required_next_value:
        counter.next_value = required_next_value
