"""Seed Trợ lý Vận hành: đơn vị Hệ thống, kho cẩm nang, trợ lý và gợi ý mặc định.

Chạy được nhiều lần. Nguyên tắc: **chỉ tạo cái còn thiếu, không bao giờ đè lên thứ super admin
đã sửa**. Nếu mỗi lần deploy lại ghi đè system prompt hay danh sách gợi ý thì chỉnh sửa của
người vận hành biến mất sau mỗi bản phát hành, và họ sẽ không bao giờ tin vào màn hình cấu hình
nữa.

Văn bản cẩm nang là ngoại lệ có kiểm soát: nếu nội dung tệp đổi thì tải lại và lập chỉ mục lại,
so bằng kích thước tệp. Cẩm nang là tài liệu của sản phẩm, đi kèm mã nguồn, nên bản trong repo
mới là bản đúng.

    cd apps/api && .venv/bin/python -m app.seed_ops
"""

import asyncio
import uuid
from pathlib import Path

import redis
from rq import Queue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session_factory
from app.models.app import App, AppDataset
from app.models.dataset import Dataset
from app.models.document import Document, DocumentStatus
from app.models.ops_config import OPS_SYSTEM_KEY
from app.models.workspace import Workspace
from app.services.ops import (
    DEFAULT_TIPS,
    PREVIOUS_SYSTEM_PROMPTS,
    OPS_ASSISTANT_NAME,
    OPS_DATASET_NAME,
    OPS_DEFAULT_MODEL,
    OPS_SYSTEM_PROMPT,
    SYSTEM_WORKSPACE_NAME,
    get_config,
)
from app.storage import make_storage_key, upload_file

OPS_DOCS_DIR = Path(__file__).resolve().parent.parent / "seed_data" / "ops"

GREETING = ("Chào anh/chị. Tôi là trợ lý vận hành. Hỏi tôi cách làm trên hệ thống, "
            "hoặc mô tả một luồng xử lý để tôi dựng nháp cho anh/chị.")

SUGGESTIONS = [
    "Vì sao văn bản của tôi lập chỉ mục lỗi?",
    "Tạo trợ lý cho khách hàng cần lưu ý gì?",
    "Dựng giúp tôi luồng hỏi đáp tra một kho tri thức",
    "Trợ lý không gọi công cụ tôi đã gắn, vì sao?",
]


def _enqueue_index(document_id: uuid.UUID) -> bool:
    try:
        conn = redis.from_url(settings.REDIS_URL)
        Queue("querion-indexing", connection=conn).enqueue(
            "worker.tasks.index_document.index_document", str(document_id))
        return True
    except Exception as exc:  # Redis chưa lên: để 'uploaded' cho người vận hành bấm lập chỉ mục lại
        print(f"  ! không enqueue được job index ({exc}); văn bản ở trạng thái 'uploaded'")
        return False


async def seed_system_workspace(db: AsyncSession) -> Workspace:
    ws = (await db.execute(select(Workspace).where(
        Workspace.is_system.is_(True)).order_by(Workspace.created_at).limit(1))).scalar_one_or_none()
    if ws is None:
        # Có thể đã tồn tại một đơn vị trùng tên từ trước khi có cờ is_system.
        ws = (await db.execute(select(Workspace).where(
            Workspace.name == SYSTEM_WORKSPACE_NAME))).scalar_one_or_none()
    if ws is None:
        ws = Workspace(name=SYSTEM_WORKSPACE_NAME, is_system=True)
        db.add(ws)
        await db.flush()
        print(f"  + đơn vị {SYSTEM_WORKSPACE_NAME} (ẩn khỏi bộ chọn đơn vị)")
    ws.is_system = True
    await db.commit()
    return ws


async def seed_manual(db: AsyncSession, ws: Workspace) -> Dataset:
    ds = (await db.execute(select(Dataset).where(
        Dataset.workspace_id == ws.id, Dataset.name == OPS_DATASET_NAME))).scalar_one_or_none()
    if ds is None:
        ds = Dataset(workspace_id=ws.id, name=OPS_DATASET_NAME, visibility="internal",
                     description="Hướng dẫn vận hành chính nền tảng này, dành cho quản trị viên.")
        db.add(ds)
        await db.flush()
        print(f"  + kho tri thức {OPS_DATASET_NAME}")

    if not OPS_DOCS_DIR.exists():
        print(f"  ! chưa có thư mục {OPS_DOCS_DIR}, bỏ qua phần văn bản")
        await db.commit()
        return ds

    existing = {d.filename: d for d in (await db.execute(select(Document).where(
        Document.dataset_id == ds.id))).scalars().all()}

    for path in sorted(OPS_DOCS_DIR.glob("*.txt")):
        data = path.read_bytes()
        doc = existing.get(path.name)
        if doc is not None and doc.size == len(data):
            continue  # nội dung không đổi
        if doc is not None:
            # Cẩm nang đi kèm mã nguồn, nên bản trong repo là bản đúng: tải đè và lập chỉ mục lại.
            upload_file(doc.storage_key, data, "text/plain")
            doc.size = len(data)
            doc.status = DocumentStatus.indexing
            await db.flush()
            if not _enqueue_index(doc.id):
                doc.status = DocumentStatus.uploaded
            print(f"    ~ cập nhật {path.name}")
            continue

        doc_id = uuid.uuid4()
        key = make_storage_key(str(ws.id), str(ds.id), str(doc_id), path.name)
        upload_file(key, data, "text/plain")
        db.add(Document(id=doc_id, dataset_id=ds.id, filename=path.name, content_type="text/plain",
                        size=len(data), storage_key=key, status=DocumentStatus.indexing,
                        doc_type="huong_dan", version="v1.0", effective_from="01/10/2026"))
        await db.flush()
        if not _enqueue_index(doc_id):
            doc = await db.get(Document, doc_id)
            doc.status = DocumentStatus.uploaded
        print(f"    + {path.name}")

    await db.commit()
    return ds


async def seed_assistant(db: AsyncSession, ws: Workspace, ds: Dataset) -> App:
    app = (await db.execute(select(App).where(App.system_key == OPS_SYSTEM_KEY))).scalar_one_or_none()
    created = app is None
    if created:
        app = App(
            workspace_id=ws.id, name=OPS_ASSISTANT_NAME, system_key=OPS_SYSTEM_KEY,
            description="Trợ lý hỗ trợ quản trị viên vận hành hệ thống.",
            audience="staff", is_published=True,
            system_prompt=OPS_SYSTEM_PROMPT,
            # Soạn luồng là việc xuất JSON có cấu trúc; model hội thoại hằng ngày làm không đạt.
            model_config_json={"model": OPS_DEFAULT_MODEL},
            widget_config={"greeting": GREETING, "suggestions": SUGGESTIONS,
                           "primary_color": "#ee6d1f", "title": OPS_ASSISTANT_NAME},
            agent_enabled=True,
        )
        db.add(app)
        await db.flush()
        print(f"  + trợ lý {OPS_ASSISTANT_NAME} (model {OPS_DEFAULT_MODEL})")
    else:
        # Không đè cấu hình super admin đã sửa; chỉ đảm bảo các bất biến.
        app.workspace_id = ws.id
        app.is_published = True
        app.agent_enabled = True
        # Prompt còn y nguyên một bản mặc định cũ nghĩa là chưa ai sửa, nên nâng lên bản mới.
        # Chỉnh sửa của super admin không bao giờ khớp byte-to-byte nên luôn được giữ lại.
        if (app.system_prompt or "") in PREVIOUS_SYSTEM_PROMPTS:
            app.system_prompt = OPS_SYSTEM_PROMPT
            print("    ~ nâng system prompt lên bản mặc định mới (chưa ai sửa)")

    bound = (await db.execute(select(AppDataset).where(
        AppDataset.app_id == app.id, AppDataset.dataset_id == ds.id))).scalar_one_or_none()
    if bound is None:
        db.add(AppDataset(app_id=app.id, dataset_id=ds.id, position=0))
        print("    + gắn kho cẩm nang vào trợ lý")

    await db.commit()
    return app


async def main() -> None:
    print("Seed Trợ lý Vận hành…")
    async with async_session_factory() as db:
        ws = await seed_system_workspace(db)
        ds = await seed_manual(db, ws)
        app = await seed_assistant(db, ws, ds)

        cfg = await get_config(db)
        if not cfg.tips:
            cfg.tips = list(DEFAULT_TIPS)
            print(f"  + {len(DEFAULT_TIPS)} gợi ý mặc định")
        await db.commit()

        print(f"\nXong. Trợ lý id={app.id}, kho id={ds.id}, đơn vị id={ws.id}")
        print("Bong bóng hiện cho: " + ", ".join(cfg.audience_roles or []))
        print("Cấu hình tại /admin/ops (chỉ super admin).")


if __name__ == "__main__":
    asyncio.run(main())
