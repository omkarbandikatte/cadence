"""Declarative base and shared column helpers for every table in docs/03-DATA-MODEL.md."""
from sqlalchemy.orm import DeclarativeBase
from ulid import ULID


class Base(DeclarativeBase):
    pass


def new_id(prefix: str) -> str:
    """Prefixed ULID, e.g. mnd_01H... — see docs/03-DATA-MODEL.md."""
    return f"{prefix}_{ULID()}"
