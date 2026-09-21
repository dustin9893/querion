"""Quản lý kỹ năng của trợ lý.

Cùng luật phân quyền với công cụ, vì cùng bài toán: tài nguyên thuộc một đơn vị, sửa cần `editor`,
mở ra toàn ngân hàng hoặc mở cho kênh khách hàng cần `owner`. Lý do giống hệt: kỹ năng của Khối Tín
dụng không được tự trôi sang Khối Vận hành, và thứ khách hàng đọc được phải có người chịu trách nhiệm.

Kỹ năng đối xử như một văn bản hướng dẫn: có phiên bản, ngày hiệu lực, người soạn, người duyệt, và
hai trạng thái nháp/đã công bố. Chỉ kỹ năng đã công bố mới được trợ lý dùng.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import WorkspaceContext, require_ws_role
from app.deps import get_db
from app.models.app import App
from app.models.dataset import Dataset
from app.models.document import Document
from app.models.skill import MAX_DESCRIPTION, AppSkill, Skill
from app.models.tool import Tool
from app.models.user_workspace import WsRole
from app.services.skills import (
    BODY_TEMPLATE,
    as_vector,
    app_skills,
    as_uuid_list,
    embed_description,
    export_zip,
    find_overlaps,
    parse_skill_md,
    parse_zip,
    preselect,
    score_description,
    suggest_slug,
    to_skill_md,
    validate_body,
    validate_slug,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["skills"])

MAX_IMPORT = 50


# ---------------------------------------------------------------------------
# Lược đồ
# ---------------------------------------------------------------------------

class SkillIn(BaseModel):
    slug: str | None = None
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1, max_length=MAX_DESCRIPTION)
    body: str = ""
    version: str = Field("v1.0", max_length=32)
    effective_from: str | None = Field(None, max_length=32)
    status: str | None = None
    share_scope: str | None = None
    allow_customer: bool | None = None
    preferred_dataset_ids: list[str] | None = None
    allowed_tool_ids: list[str] | None = None
    reference_document_ids: list[str] | None = None


class SkillPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, min_length=1, max_length=MAX_DESCRIPTION)
    body: str | None = None
    version: str | None = Field(None, max_length=32)
    effective_from: str | None = Field(None, max_length=32)
    status: str | None = None
    share_scope: str | None = None
    allow_customer: bool | None = None
    preferred_dataset_ids: list[str] | None = None
    allowed_tool_ids: list[str] | None = None
    reference_document_ids: list[str] | None = None


class SkillOut(BaseModel):
    id: str
    workspace_id: str
    slug: str
    name: str
    description: str
    body: str
    version: str
    effective_from: str | None
    status: str
    share_scope: str
    allow_customer: bool
    preferred_dataset_ids: list[str]
    allowed_tool_ids: list[str]
    reference_document_ids: list[str]
    app_count: int = 0
    own_unit: bool = True
    quality: dict | None = None
    overlaps: list[dict] = []
    created_at: str
    updated_at: str


def _out(skill: Skill, *, own_unit: bool = True, app_count: int = 0,
         overlaps: list[dict] | None = None) -> SkillOut:
    score = score_description(skill.description)
    return SkillOut(
        id=str(skill.id), workspace_id=str(skill.workspace_id), slug=skill.slug, name=skill.name,
        description=skill.description, body=skill.body or "", version=skill.version,
        effective_from=skill.effective_from, status=skill.status, share_scope=skill.share_scope,
        allow_customer=skill.allow_customer,
        preferred_dataset_ids=[str(x) for x in (skill.preferred_dataset_ids or [])],
        allowed_tool_ids=[str(x) for x in (skill.allowed_tool_ids or [])],
        reference_document_ids=[str(x) for x in (skill.reference_document_ids or [])],
        app_count=app_count, own_unit=own_unit,
        quality={"level": score.level, "problems": score.problems, "hints": score.hints},
        overlaps=overlaps or [],
        created_at=skill.created_at.isoformat(), updated_at=skill.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------

async def _load_own(db: AsyncSession, skill_id: str, ws: WorkspaceContext) -> Skill:
    """Kỹ năng của chính đơn vị này. Sửa kỹ năng đơn vị khác là 404, không phải 403."""
    try:
        skill = await db.get(Skill, uuid.UUID(skill_id))
    except (ValueError, TypeError):
        skill = None
    if skill is None or skill.workspace_id != ws.workspace_id:
        raise HTTPException(404, "Không tìm thấy kỹ năng")
    return skill


def _require_owner(ws: WorkspaceContext, what: str) -> None:
    if ws.ws_role != WsRole.owner:
        raise HTTPException(403, f"Chỉ chủ sở hữu đơn vị mới {what}")


async def _check_references(db: AsyncSession, ws: WorkspaceContext, data: dict) -> None:
    """Kho, công cụ và văn bản tham chiếu phải thuộc đúng đơn vị này."""
    ds = as_uuid_list(data.get("preferred_dataset_ids"))
    if ds:
        found = (await db.execute(select(func.count()).select_from(Dataset).where(
            Dataset.id.in_(ds), Dataset.workspace_id == ws.workspace_id))).scalar() or 0
        if found != len(ds):
            raise HTTPException(400, "Có kho tri thức không thuộc đơn vị này")
    tools = as_uuid_list(data.get("allowed_tool_ids"))
    if tools:
        found = (await db.execute(select(func.count()).select_from(Tool).where(
            Tool.id.in_(tools),
            or_(Tool.workspace_id == ws.workspace_id,
                (Tool.share_scope == "bank") & Tool.is_active.is_(True))))).scalar() or 0
        if found != len(tools):
            raise HTTPException(400, "Có công cụ đơn vị này không dùng được")
    docs = as_uuid_list(data.get("reference_document_ids"))
    if docs:
        found = (await db.execute(select(func.count()).select_from(Document)
                                  .join(Dataset, Document.dataset_id == Dataset.id).where(
            Document.id.in_(docs), Dataset.workspace_id == ws.workspace_id))).scalar() or 0
        if found != len(docs):
            raise HTTPException(400, "Có văn bản tham chiếu không thuộc đơn vị này")


def _apply_scope_fields(skill: Skill, data: dict, ws: WorkspaceContext) -> None:
    if data.get("share_scope") is not None and data["share_scope"] != skill.share_scope:
        if data["share_scope"] not in ("unit", "bank"):
            raise HTTPException(400, "Phạm vi chia sẻ phải là 'unit' hoặc 'bank'")
        _require_owner(ws, "chia sẻ kỹ năng ra toàn ngân hàng")
        skill.share_scope = data["share_scope"]
    if data.get("allow_customer") is not None and data["allow_customer"] != skill.allow_customer:
        _require_owner(ws, "mở kỹ năng cho kênh khách hàng")
        skill.allow_customer = bool(data["allow_customer"])
    if data.get("status") is not None:
        if data["status"] not in ("draft", "published"):
            raise HTTPException(400, "Trạng thái phải là 'draft' hoặc 'published'")
        skill.status = data["status"]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("/skills", response_model=list[SkillOut])
async def list_skills(
    ws: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
    include_bank: bool = Query(True),
):
    """Kỹ năng của đơn vị, cộng kỹ năng đã công bố và chia sẻ toàn ngân hàng."""
    cond = [Skill.workspace_id == ws.workspace_id]
    if include_bank:
        cond.append((Skill.share_scope == "bank") & (Skill.status == "published"))
    rows = (await db.execute(select(Skill).where(or_(*cond)).order_by(Skill.name))).scalars().all()
    counts = dict((await db.execute(
        select(AppSkill.skill_id, func.count()).group_by(AppSkill.skill_id))).all())
    return [_out(s, own_unit=s.workspace_id == ws.workspace_id, app_count=counts.get(s.id, 0))
            for s in rows]


@router.get("/skills/template")
async def body_template(ws: WorkspaceContext = Depends(require_ws_role(WsRole.viewer))):
    """Khung thân bài gợi ý sẵn cho trình soạn."""
    return {"body": BODY_TEMPLATE}


@router.post("/skills", response_model=SkillOut, status_code=201)
async def create_skill(
    body: SkillIn,
    ws: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump()
    slug = validate_slug(data.get("slug") or suggest_slug(data["name"]))
    dup = (await db.execute(select(Skill.id).where(
        Skill.workspace_id == ws.workspace_id, Skill.slug == slug))).scalar_one_or_none()
    if dup:
        raise HTTPException(409, "Đơn vị đã có kỹ năng với mã này")
    await _check_references(db, ws, data)

    skill = Skill(
        workspace_id=ws.workspace_id, slug=slug, name=data["name"].strip(),
        description=data["description"].strip(), body=validate_body(data.get("body") or ""),
        version=data.get("version") or "v1.0", effective_from=data.get("effective_from"),
        preferred_dataset_ids=as_uuid_list(data.get("preferred_dataset_ids")),
        allowed_tool_ids=as_uuid_list(data.get("allowed_tool_ids")),
        reference_document_ids=as_uuid_list(data.get("reference_document_ids")),
        created_by=ws.user.id,
    )
    _apply_scope_fields(skill, data, ws)
    skill.description_embedding = await embed_description(db, skill.description)
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    overlaps = await find_overlaps(db, skill, as_vector(skill.description_embedding))
    return _out(skill, overlaps=overlaps)


@router.get("/skills/{skill_id}", response_model=SkillOut)
async def get_skill(
    skill_id: str,
    ws: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    try:
        skill = await db.get(Skill, uuid.UUID(skill_id))
    except (ValueError, TypeError):
        skill = None
    own = skill is not None and skill.workspace_id == ws.workspace_id
    shared = skill is not None and skill.share_scope == "bank" and skill.status == "published"
    if skill is None or not (own or shared):
        raise HTTPException(404, "Không tìm thấy kỹ năng")
    count = (await db.execute(select(func.count()).select_from(AppSkill)
                              .where(AppSkill.skill_id == skill.id))).scalar() or 0
    overlaps = await find_overlaps(db, skill, as_vector(skill.description_embedding)) if own else []
    return _out(skill, own_unit=own, app_count=count, overlaps=overlaps)


@router.patch("/skills/{skill_id}", response_model=SkillOut)
async def update_skill(
    skill_id: str,
    body: SkillPatch,
    ws: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    skill = await _load_own(db, skill_id, ws)
    data = body.model_dump(exclude_unset=True)
    await _check_references(db, ws, data)

    if "name" in data and data["name"]:
        skill.name = data["name"].strip()
    if "description" in data and data["description"]:
        new_desc = data["description"].strip()
        if new_desc != skill.description:
            skill.description = new_desc
            skill.description_embedding = await embed_description(db, new_desc)
    if "body" in data and data["body"] is not None:
        skill.body = validate_body(data["body"])
    if data.get("version"):
        skill.version = data["version"]
    if "effective_from" in data:
        skill.effective_from = data["effective_from"]
    for field in ("preferred_dataset_ids", "allowed_tool_ids", "reference_document_ids"):
        if field in data and data[field] is not None:
            setattr(skill, field, as_uuid_list(data[field]))
    _apply_scope_fields(skill, data, ws)
    if skill.status == "published" and skill.approved_by is None:
        skill.approved_by = ws.user.id
    skill.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(skill)
    overlaps = await find_overlaps(db, skill, as_vector(skill.description_embedding))
    return _out(skill, overlaps=overlaps)


@router.delete("/skills/{skill_id}", status_code=200)
async def delete_skill(
    skill_id: str,
    ws: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    skill = await _load_own(db, skill_id, ws)
    await db.delete(skill)
    await db.commit()
    return {"detail": "Đã xoá kỹ năng"}


# ---------------------------------------------------------------------------
# Thử kỹ năng
# ---------------------------------------------------------------------------

class TryIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    app_id: str | None = None


@router.post("/skills/try")
async def try_skills(
    body: TryIn,
    ws: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Gõ một câu, xem kỹ năng nào sẽ được kích hoạt và điểm khớp là bao nhiêu.

    Thử được trước khi gắn vào trợ lý, nên người soạn sửa mô tả rồi thử lại ngay trong trang.
    """
    if body.app_id:
        try:
            app = await db.get(App, uuid.UUID(body.app_id))
        except (ValueError, TypeError):
            app = None
        if app is None or app.workspace_id != ws.workspace_id:
            raise HTTPException(404, "Không tìm thấy trợ lý")
        skills = await app_skills(db, app)
    else:
        app = App(workspace_id=ws.workspace_id, name="thử", skill_match_threshold=0.32)
        skills = (await db.execute(select(Skill).where(
            Skill.workspace_id == ws.workspace_id, Skill.status == "published")
            .order_by(Skill.name))).scalars().all()

    if not skills:
        return {"chosen": None, "threshold": float(getattr(app, "skill_match_threshold", 0.32)),
                "scores": [], "note": "Chưa có kỹ năng nào đã công bố để thử"}

    from app.services.skills import cosine

    vec = await embed_description(db, body.query)
    scores = []
    for s in skills:
        score = cosine(vec or [], as_vector(s.description_embedding)) if vec else 0.0
        scores.append({"id": str(s.id), "slug": s.slug, "name": s.name, "score": round(score, 3)})
    scores.sort(key=lambda r: -r["score"])
    chosen, best = await preselect(db, app, body.query, skills)
    return {
        "chosen": None if chosen is None else {"id": str(chosen.id), "slug": chosen.slug, "name": chosen.name},
        "best_score": best,
        "threshold": float(getattr(app, "skill_match_threshold", 0.32)),
        "scores": scores[:10],
    }


# ---------------------------------------------------------------------------
# Xuất / nhập theo chuẩn agentskills.io
# ---------------------------------------------------------------------------

@router.get("/skills/{skill_id}/export")
async def export_one(
    skill_id: str,
    ws: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Một kỹ năng thành tệp SKILL.md đúng chuẩn, chạy được trên agent khác."""
    skill = await _load_own(db, skill_id, ws)
    return Response(
        content=to_skill_md(skill), media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{skill.slug}-SKILL.md"'})


@router.get("/skills-export")
async def export_all(
    ws: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Toàn bộ kỹ năng của đơn vị thành một zip, mỗi kỹ năng một thư mục theo bố cục chuẩn."""
    rows = (await db.execute(select(Skill).where(
        Skill.workspace_id == ws.workspace_id).order_by(Skill.slug))).scalars().all()
    if not rows:
        raise HTTPException(404, "Đơn vị chưa có kỹ năng nào")
    return Response(
        content=export_zip(rows), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="ky-nang.zip"'})


@router.post("/skills-import")
async def import_skills(
    file: UploadFile = File(...),
    ws: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Nhập một SKILL.md hoặc một zip nhiều kỹ năng. Kỹ năng nhập về luôn ở trạng thái nháp."""
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(400, "Tệp quá lớn, tối đa 5 MB")
    name = (file.filename or "").lower()
    parsed = parse_zip(raw) if name.endswith(".zip") else [parse_skill_md(raw.decode("utf-8", "replace"))]
    if len(parsed) > MAX_IMPORT:
        raise HTTPException(400, f"Tối đa {MAX_IMPORT} kỹ năng mỗi lần nhập")

    created, skipped = [], []
    for item in parsed:
        exists = (await db.execute(select(Skill.id).where(
            Skill.workspace_id == ws.workspace_id, Skill.slug == item["slug"]))).scalar_one_or_none()
        if exists:
            skipped.append(item["slug"])
            continue
        skill = Skill(workspace_id=ws.workspace_id, created_by=ws.user.id, status="draft", **item)
        skill.description_embedding = await embed_description(db, skill.description)
        db.add(skill)
        created.append(item["slug"])
    await db.commit()
    return {"created": created, "skipped": skipped,
            "detail": f"Đã nhập {len(created)} kỹ năng ở trạng thái nháp"
                      + (f", bỏ qua {len(skipped)} kỹ năng trùng mã" if skipped else "")}
