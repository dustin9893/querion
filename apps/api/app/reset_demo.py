"""Xoá sạch dữ liệu nghiệp vụ rồi seed lại bộ demo chuẩn — một lệnh, có xác nhận.

    cd apps/api && .venv/bin/python -m app.reset_demo --yes

Giữ lại đúng hai thứ: `alembic_version` (schema) và `ai_providers` (khoá API đã mã hoá — nhập lại
khoá là việc thủ công, không ai muốn làm lại chỉ vì reset demo). Mọi bảng khác, kể cả `users`
(super admin được tạo lại từ biến môi trường), bảng checkpoint của LangGraph và toàn bộ object
trong bucket MinIO, đều bị xoá.

Vì sao là một script chứ không phải "xoá tay trên DB": các bảng có FK chéo và object MinIO không
có FK — xoá bảng mà quên object là rò rỉ tệp; xoá object mà quên bảng là 500 khi tải. Script này
làm cả hai theo đúng thứ tự và chạy lại được. Trên máy chủ, `deploy/remote.sh reset-demo` gọi nó
sau khi đã pg_dump.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text

from app.config import settings
from app.db import Base, async_session_factory

KEEP_TABLES = {"alembic_version", "ai_providers"}
# LangGraph tạo bảng riêng ngoài Alembic; xoá để một run cũ không resume được vào dữ liệu mới.
CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints", "checkpoint_migrations")


async def wipe_database() -> list[str]:
    import app.models  # noqa: F401 — nạp toàn bộ model để metadata đủ bảng

    tables = [t.name for t in Base.metadata.sorted_tables if t.name not in KEEP_TABLES]
    async with async_session_factory() as db:
        existing = {
            r[0] for r in (await db.execute(text(
                "select tablename from pg_tables where schemaname = 'public'"))).all()
        }
        targets = [t for t in tables if t in existing] + [t for t in CHECKPOINT_TABLES if t in existing]
        if targets:
            quoted = ", ".join(f'"{t}"' for t in targets)
            await db.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
        await db.commit()
    return targets


def wipe_bucket() -> int:
    """Xoá mọi object trong bucket demo (văn bản, logo, mẫu, báo cáo)."""
    from app.storage import _get_client

    client = _get_client()
    bucket = settings.MINIO_BUCKET
    if not client.bucket_exists(bucket):
        return 0
    names = [o.object_name for o in client.list_objects(bucket, recursive=True)]
    for name in names:
        client.remove_object(bucket, name)
    return len(names)


def flush_queues() -> None:
    """Job lập chỉ mục / báo cáo còn xếp hàng trỏ vào id đã xoá — bỏ hết."""
    try:
        import redis
        from rq import Queue

        conn = redis.from_url(settings.REDIS_URL)
        for name in ("querion-indexing", "querion-jobs"):
            Queue(name, connection=conn).empty()
    except Exception as exc:  # Redis vắng thì seed vẫn chạy được, chỉ không lập chỉ mục ngay
        print(f"  ! không dọn được hàng đợi Redis ({exc})")


async def reseed() -> None:
    from app import seed_demo, seed_ops, seed_skills

    await seed_demo.main()
    await seed_ops.main()
    await seed_skills.main()


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Xoá dữ liệu nghiệp vụ và seed lại bộ demo.")
    parser.add_argument("--yes", action="store_true", help="xác nhận xoá (bắt buộc)")
    parser.add_argument("--no-seed", action="store_true", help="chỉ xoá, không seed lại")
    args = parser.parse_args(argv)
    if not args.yes:
        print("Lệnh này XOÁ toàn bộ dữ liệu nghiệp vụ (trừ ai_providers). Thêm --yes để xác nhận.")
        return 2

    db_name = settings.DATABASE_URL.rsplit("/", 1)[-1]
    print(f"[reset_demo] xoá dữ liệu trong '{db_name}' và bucket '{settings.MINIO_BUCKET}'")
    removed = wipe_bucket()
    print(f"  - MinIO: đã xoá {removed} object")
    tables = await wipe_database()
    print(f"  - Postgres: đã truncate {len(tables)} bảng")
    flush_queues()
    if args.no_seed:
        return 0
    print("[reset_demo] seed lại")
    await reseed()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
