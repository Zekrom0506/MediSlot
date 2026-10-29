"""add delivery tracking to notifications

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28 18:02:13.880412
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('notifications', sa.Column('booking_id', sa.Integer(), nullable=True))
    op.add_column('notifications', sa.Column('attempts', sa.Integer(), server_default='0', nullable=False))
    op.add_column('notifications', sa.Column('last_error', sa.Text(), nullable=True))
    op.create_index(op.f('ix_notifications_booking_id'), 'notifications', ['booking_id'], unique=False)
    op.create_unique_constraint('uq_notifications_booking_type', 'notifications', ['booking_id', 'type'])
    op.create_foreign_key('fk_notifications_booking_id', 'notifications', 'bookings', ['booking_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_notifications_booking_id', 'notifications', type_='foreignkey')
    op.drop_constraint('uq_notifications_booking_type', 'notifications', type_='unique')
    op.drop_index(op.f('ix_notifications_booking_id'), table_name='notifications')
    op.drop_column('notifications', 'last_error')
    op.drop_column('notifications', 'attempts')
    op.drop_column('notifications', 'booking_id')
