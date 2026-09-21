"""Worker configuration — reads from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (apps/worker/../../.env)
_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(_env_path)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://querion:querion_secret@localhost:5432/querion",
).replace("+asyncpg", "")  # Worker uses sync driver

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# MinIO
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin_secret")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "querion-docs")
MINIO_USE_SSL = os.getenv("MINIO_USE_SSL", "false").lower() == "true"

# Encryption
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

# Queue
QUEUE_NAME = "querion-indexing"
