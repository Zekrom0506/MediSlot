"""create initial tables

Revision ID: 0001
Revises: 
Create Date: 2026-09-13 18:20:41.512094
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('clinics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('address', sa.String(length=255), nullable=False),
    sa.Column('city', sa.String(length=80), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clinics_city'), 'clinics', ['city'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('patient', 'doctor', 'admin', name='userrole_values', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('phone_number', sa.String(length=20), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('doctors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('clinic_id', sa.Integer(), nullable=False),
    sa.Column('specialty', sa.String(length=80), nullable=False),
    sa.Column('years_of_experience', sa.Integer(), nullable=False),
    sa.Column('consultation_fee', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('appointment_length_minutes', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_doctors_clinic_id'), 'doctors', ['clinic_id'], unique=False)
    op.create_index(op.f('ix_doctors_specialty'), 'doctors', ['specialty'], unique=False)
    op.create_table('idempotency_keys',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('response_status_code', sa.Integer(), nullable=False),
    sa.Column('response_body', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_index(op.f('ix_idempotency_keys_created_at'), 'idempotency_keys', ['created_at'], unique=False)
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.Enum('confirmation', 'cancellation', 'reminder', name='notificationtype_values', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('channel', sa.Enum('email', 'sms', name='notificationchannel_values', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('status', sa.Enum('pending', 'sent', 'failed', name='notificationstatus_values', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_table('slots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('doctor_id', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Enum('available', 'booked', 'blocked', name='slotstatus_values', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('doctor_id', 'start_time', name='uq_slots_doctor_start_time')
    )
    op.create_table('weekly_schedules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('doctor_id', sa.Integer(), nullable=False),
    sa.Column('day_of_week', sa.SmallInteger(), nullable=False),
    sa.Column('start_time', sa.Time(), nullable=False),
    sa.Column('end_time', sa.Time(), nullable=False),
    sa.CheckConstraint('day_of_week BETWEEN 0 AND 6', name='ck_schedule_day_of_week'),
    sa.CheckConstraint('start_time < end_time', name='ck_schedule_start_before_end'),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_weekly_schedules_doctor_id'), 'weekly_schedules', ['doctor_id'], unique=False)
    op.create_table('bookings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('slot_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('confirmed', 'cancelled', 'completed', 'no_show', name='bookingstatus_values', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('reason_for_visit', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['slot_id'], ['slots.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bookings_patient_id'), 'bookings', ['patient_id'], unique=False)
    op.create_index(op.f('ix_bookings_slot_id'), 'bookings', ['slot_id'], unique=False)
    op.create_index('uq_bookings_one_confirmed_per_slot', 'bookings', ['slot_id'], unique=True, postgresql_where=sa.text("status = 'confirmed'"))


def downgrade() -> None:
    op.drop_index('uq_bookings_one_confirmed_per_slot', table_name='bookings', postgresql_where=sa.text("status = 'confirmed'"))
    op.drop_index(op.f('ix_bookings_slot_id'), table_name='bookings')
    op.drop_index(op.f('ix_bookings_patient_id'), table_name='bookings')
    op.drop_table('bookings')
    op.drop_index(op.f('ix_weekly_schedules_doctor_id'), table_name='weekly_schedules')
    op.drop_table('weekly_schedules')
    op.drop_table('slots')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_idempotency_keys_created_at'), table_name='idempotency_keys')
    op.drop_table('idempotency_keys')
    op.drop_index(op.f('ix_doctors_specialty'), table_name='doctors')
    op.drop_index(op.f('ix_doctors_clinic_id'), table_name='doctors')
    op.drop_table('doctors')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_clinics_city'), table_name='clinics')
    op.drop_table('clinics')
