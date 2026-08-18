"""add reopened to reportstatus enum

Revision ID: a9f64836b730
Revises: fd70736190d2
Create Date: 2026-08-17 19:09:07.327723
"""
from alembic import op
import sqlalchemy as sa


revision = 'a9f64836b730'
down_revision = 'fd70736190d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL: extend the enum type. SQLite stores enums as VARCHAR (no-op).
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE reportstatus ADD VALUE IF NOT EXISTS 'reopened'")


def downgrade() -> None:
    # PostgreSQL cannot drop enum values in-place; documented irreversible.
    pass
