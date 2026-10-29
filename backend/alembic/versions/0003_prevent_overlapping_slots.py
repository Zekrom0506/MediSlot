"""prevent overlapping slots, track reschedules and who cancelled

- Replaces the (doctor_id, start_time) unique constraint with an exclusion
  constraint: a doctor can never have two live slots whose times overlap.
- Adds the "retired" slot status and the "rescheduled" booking status.
- Adds bookings.cancelled_by (patient or clinic).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28 08:30:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def replace_check(table: str, name: str, column: str, values: list[str]) -> None:
    allowed = ", ".join(f"'{value}'" for value in values)
    op.drop_constraint(name, table, type_='check')
    op.create_check_constraint(name, table, f"{column} IN ({allowed})")


def upgrade() -> None:
    # btree_gist lets one GiST index combine "same doctor" (=) with "times overlap" (&&).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    replace_check('slots', 'slotstatus_values', 'status', ['available', 'booked', 'blocked', 'retired'])
    op.drop_constraint('uq_slots_doctor_start_time', 'slots', type_='unique')
    op.execute(
        "ALTER TABLE slots ADD CONSTRAINT ex_slots_no_overlap "
        "EXCLUDE USING gist (doctor_id WITH =, tstzrange(start_time, end_time) WITH &&) "
        "WHERE (status <> 'retired')"
    )

    replace_check(
        'bookings', 'bookingstatus_values', 'status',
        ['confirmed', 'cancelled', 'completed', 'no_show', 'rescheduled'],
    )
    op.add_column(
        'bookings',
        sa.Column(
            'cancelled_by',
            sa.Enum('patient', 'clinic', name='cancelledby_values', native_enum=False,
                    create_constraint=True, length=20),
            nullable=True,
        ),
    )
    op.execute("UPDATE bookings SET cancelled_by = 'patient' WHERE status = 'cancelled'")


def downgrade() -> None:
    op.drop_column('bookings', 'cancelled_by')
    op.execute("UPDATE bookings SET status = 'cancelled' WHERE status = 'rescheduled'")
    replace_check('bookings', 'bookingstatus_values', 'status', ['confirmed', 'cancelled', 'completed', 'no_show'])

    op.execute("ALTER TABLE slots DROP CONSTRAINT ex_slots_no_overlap")
    op.execute("UPDATE slots SET status = 'blocked' WHERE status = 'retired'")
    op.create_unique_constraint('uq_slots_doctor_start_time', 'slots', ['doctor_id', 'start_time'])
    replace_check('slots', 'slotstatus_values', 'status', ['available', 'booked', 'blocked'])
