"""Index document task — orchestrates the full pipeline."""

import os
import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from worker.db import get_db
from worker.pipeline.downloader import download
from worker.pipeline.route import build_chunks
from worker.pipeline.embedder import embed_texts

logger = logging.getLogger(__name__)


def index_document(document_id: str) -> None:
    """Full indexing pipeline for a single document.

    Steps:
    1. Fetch document + active AI provider from DB
    2. Download file from MinIO
    3. Parse text
    4. Chunk text
    5. Embed chunks (OpenAI)
    6. Store chunks + embeddings in DB
    7. Update document status → ready
    """
    db = get_db()
    doc_id = uuid.UUID(document_id)

    try:
        # --- 1. Fetch document ---
        from sqlalchemy import text as sql_text

        row = db.execute(
            sql_text(
                "SELECT id, dataset_id, filename, content_type, storage_key, status "
                "FROM documents WHERE id = :id"
            ),
            {"id": doc_id},
        ).fetchone()

        if not row:
            logger.error(f"Document {document_id} not found")
            return

        dataset_id = row.dataset_id
        filename = row.filename
        content_type = row.content_type
        storage_key = row.storage_key

        logger.info(f"Indexing document: {filename} ({document_id})")

        # --- Fetch active embedding provider ---
        provider_row = db.execute(
            sql_text(
                "SELECT provider_name, api_key_encrypted, model_name, base_url FROM ai_providers "
                "WHERE is_active = true AND purpose = 'embedding' ORDER BY created_at LIMIT 1"
            )
        ).fetchone()

        if not provider_row:
            _mark_failed(db, doc_id, "No active embedding provider configured")
            return

        provider_name = provider_row.provider_name
        api_key_encrypted = provider_row.api_key_encrypted
        model_name = provider_row.model_name
        base_url = provider_row.base_url

        # --- 2. Download ---
        logger.info(f"Downloading from MinIO: {storage_key}")
        file_path = download(storage_key)

        try:
            # --- 3-4. Parse + chunk ---
            logger.info(f"Parsing: {filename}")
            try:
                chunks = build_chunks(file_path, content_type)
            except ValueError as e:
                _mark_failed(db, doc_id, str(e))
                return

            logger.info(f"Created {len(chunks)} chunks")

            # --- 5. Embed ---
            logger.info(f"Embedding {len(chunks)} chunks with {model_name}")
            texts = [c.content for c in chunks]
            meter: dict = {}
            embeddings = embed_texts(texts, api_key_encrypted, model_name, provider_name, base_url=base_url, meter=meter)
            _record_usage(db, dataset_id, doc_id, provider_name, model_name, texts, meter)

            # --- 6. Store chunks + embeddings ---
            logger.info("Storing chunks and embeddings in DB")

            # Clear old chunks/embeddings for this document
            db.execute(
                sql_text("DELETE FROM chunks WHERE document_id = :doc_id"),
                {"doc_id": doc_id},
            )

            for chunk, embedding_vec in zip(chunks, embeddings):
                chunk_id = uuid.uuid4()
                db.execute(
                    sql_text("""
                        INSERT INTO chunks (id, dataset_id, document_id, chunk_index, content, created_at)
                        VALUES (:id, :dataset_id, :document_id, :chunk_index, :content, :created_at)
                    """),
                    {
                        "id": chunk_id,
                        "dataset_id": dataset_id,
                        "document_id": doc_id,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "created_at": datetime.now(timezone.utc),
                    },
                )

                # Store embedding as pgvector format string
                vec_str = "[" + ",".join(str(v) for v in embedding_vec) + "]"
                db.execute(
                    sql_text("""
                        INSERT INTO embeddings (chunk_id, embedding, model_name, created_at)
                        VALUES (:chunk_id, :embedding, :model_name, :created_at)
                    """),
                    {
                        "chunk_id": chunk_id,
                        "embedding": vec_str,
                        "model_name": model_name,
                        "created_at": datetime.now(timezone.utc),
                    },
                )

            # --- 7. Update document status ---
            db.execute(
                sql_text("""
                    UPDATE documents
                    SET status = 'ready', chunk_count = :count, error_message = NULL,
                        updated_at = :now
                    WHERE id = :id
                """),
                {
                    "count": len(chunks),
                    "now": datetime.now(timezone.utc),
                    "id": doc_id,
                },
            )
            db.commit()
            logger.info(f"Document {document_id} indexed successfully: {len(chunks)} chunks")

        finally:
            # Clean up temp file
            if os.path.exists(file_path):
                os.unlink(file_path)

    except Exception as e:
        logger.exception(f"Failed to index document {document_id}")
        _mark_failed(db, doc_id, str(e))
    finally:
        db.close()


CHARS_PER_TOKEN = 3  # same estimate as app/services/usage.py


def _record_usage(db, dataset_id, doc_id: uuid.UUID, provider_name: str, model_name: str,
                  texts: list[str], meter: dict) -> None:
    """Meter the embedding tokens of this indexing job (committed at once: the tokens are spent
    even if storing the chunks fails later). Never fails the job."""
    from sqlalchemy import text as sql_text

    try:
        reported = meter.get("tokens")
        tokens = reported if reported is not None else sum((len(t) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN for t in texts)
        db.execute(
            sql_text("""
                INSERT INTO token_usage (id, created_at, workspace_id, dataset_id, document_id, channel, component,
                                         purpose, provider, model, prompt_tokens, completion_tokens, total_tokens,
                                         calls, estimated)
                SELECT :id, :now, d.workspace_id, d.id, :doc_id, 'indexing', 'document_embedding',
                       'embedding', :provider, :model, :tokens, 0, :tokens, :calls, :estimated
                FROM datasets d WHERE d.id = :dataset_id
            """),
            {"id": uuid.uuid4(), "now": datetime.now(timezone.utc), "doc_id": doc_id, "provider": provider_name,
             "model": model_name, "tokens": int(tokens), "calls": max(1, meter.get("calls", 1)),
             "estimated": reported is None, "dataset_id": dataset_id},
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("could not record token usage for document %s", doc_id, exc_info=True)


def _mark_failed(db, doc_id: uuid.UUID, error: str) -> None:
    """Mark document as failed with error message."""
    from sqlalchemy import text as sql_text

    db.execute(
        sql_text("""
            UPDATE documents
            SET status = 'failed', error_message = :error, updated_at = :now
            WHERE id = :id
        """),
        {"error": error[:500], "now": datetime.now(timezone.utc), "id": doc_id},
    )
    db.commit()
    logger.error(f"Document {doc_id} marked as failed: {error}")
