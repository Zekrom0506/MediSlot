import enum

from sqlalchemy import Enum
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Parent class for every database table."""


def enum_column(enum_class: type[enum.Enum]) -> Enum:
    """Store a Python enum as a plain VARCHAR with a CHECK constraint.

    A non-native enum is easier to change later than a Postgres ENUM type,
    and storing the value ("confirmed") instead of the name keeps raw SQL readable.
    """
    allowed_values = [member.value for member in enum_class]
    return Enum(
        *allowed_values,
        name=f"{enum_class.__name__.lower()}_values",
        native_enum=False,
        create_constraint=True,
        length=20,
    )
