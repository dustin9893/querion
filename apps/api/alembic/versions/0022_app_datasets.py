"""An assistant can read several knowledge bases: app_datasets replaces apps.dataset_id

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_datasets",
        sa.Column("app_id", UUID(as_uuid=True), sa.ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),  # order chosen in the admin UI
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_app_datasets_dataset_id", "app_datasets", ["dataset_id"])
    # Keep every existing binding, then drop the single-dataset column so there is one source of truth.
    op.execute("INSERT INTO app_datasets (app_id, dataset_id, position) "
               "SELECT id, dataset_id, 0 FROM apps WHERE dataset_id IS NOT NULL")
    op.drop_column("apps", "dataset_id")


def downgrade() -> None:
    op.add_column("apps", sa.Column(
        "dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True,
    ))
    op.execute("UPDATE apps SET dataset_id = (SELECT ad.dataset_id FROM app_datasets ad "
               "WHERE ad.app_id = apps.id ORDER BY ad.position LIMIT 1)")
    op.drop_index("ix_app_datasets_dataset_id", table_name="app_datasets")
    op.drop_table("app_datasets")
