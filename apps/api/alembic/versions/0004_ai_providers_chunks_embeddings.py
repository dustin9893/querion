"""Add ai_providers, chunks, embeddings tables + pgvector extension

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ai_providers table
    op.create_table(
        "ai_providers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("provider_name", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("api_key_encrypted", sa.Text, nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # chunks table
    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chunks_dataset_document", "chunks", ["dataset_id", "document_id"])

    # embeddings table — uses raw SQL for vector column
    op.execute("""
        CREATE TABLE embeddings (
            chunk_id UUID PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
            embedding vector(1536) NOT NULL,
            model_name VARCHAR(128) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # HNSW index for cosine similarity search
    op.execute("""
        CREATE INDEX ix_embeddings_hnsw ON embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_embeddings_hnsw")
    op.execute("DROP TABLE IF EXISTS embeddings")
    op.drop_index("ix_chunks_dataset_document", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("ai_providers")
