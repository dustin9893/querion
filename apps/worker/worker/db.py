"""Sync SQLAlchemy session for worker (RQ runs synchronously)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from worker.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Session:
    """Get a sync DB session."""
    return SessionLocal()
