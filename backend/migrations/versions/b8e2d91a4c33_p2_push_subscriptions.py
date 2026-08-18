"""p2: web push subscriptions + video frame signatures

Revision ID: b8e2d91a4c33
Revises: 156f792574f9
Create Date: 2026-08-18
"""
import sqlalchemy as sa
from alembic import op

revision = "b8e2d91a4c33"
down_revision = "156f792574f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "endpoint"),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])
    # multi-frame perceptual signatures for the video_embedding duplicate analyzer
    with op.batch_alter_table("report_media") as batch:
        batch.add_column(sa.Column("frame_sigs", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("report_media") as batch:
        batch.drop_column("frame_sigs")
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
