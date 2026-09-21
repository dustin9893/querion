"""Kỹ năng: kiểm theo chuẩn, đo chất lượng, cảnh báo chồng chéo, chọn trước, xuất nhập SKILL.md.

Hai việc khó của tính năng này không nằm ở chỗ lưu trữ.

Thứ nhất là **mô tả "dùng khi nào"**. Nó là thứ duy nhất mô hình đọc để quyết định có kích hoạt kỹ
năng hay không, nên một mô tả mơ hồ làm hỏng cả kỹ năng dù thân bài viết hay tới đâu. `score_description`
chấm điểm ngay lúc soạn để người viết sửa trước khi lưu.

Thứ hai là **chồng chéo**. Hai kỹ năng mô tả gần giống nhau thì mô hình chọn nhầm, và người dùng
không bao giờ hiểu vì sao. `find_overlaps` so embedding của mô tả ngay lúc lưu và cảnh báo.

Chọn trước (`preselect`) dành cho trợ lý RAG thuần, loại không bật agent: máy chủ tự so câu hỏi với
mô tả rồi nạp thẳng kỹ năng khớp nhất vào prompt. Không tốn thêm một vòng gọi mô hình, nên kênh cán
bộ và khách hàng giữ nguyên độ trễ. Trợ lý có agent thì dùng công cụ `kich_hoat_ky_nang` để tự quyết.
"""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from dataclasses import dataclass
from typing import Any

import yaml
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app import App
from app.models.skill import MAX_BODY_LINES, MAX_DESCRIPTION, MAX_SLUG, AppSkill, Skill

# Chuẩn agentskills.io: chữ thường, số, gạch nối; không mở đầu/kết thúc bằng gạch, không gạch đôi.
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

#: Mô tả ngắn hơn ngần này gần như chắc chắn không đủ để phân biệt với kỹ năng khác.
MIN_DESCRIPTION = 40
#: Trên mức này coi như hai kỹ năng nói cùng một chuyện.
OVERLAP_THRESHOLD = 0.86

#: Khung thân bài gợi ý sẵn trong trình soạn. Năm mục này phản ánh đúng thứ mô hình cần.
BODY_TEMPLATE = """## Khi nào dùng

<Mô tả tình huống cụ thể. Ví dụ: cán bộ hỏi một hồ sơ đã đủ điều kiện giải ngân chưa.>

## Các bước

1. <Bước một>
2. <Bước hai>

## Quy tắc bắt buộc

- Luôn trích dẫn Điều/Khoản của văn bản, không kết luận suông.
- Không tự quyết định phê duyệt hay từ chối; chỉ nêu còn thiếu gì.

## Ví dụ

**Hỏi:** <câu hỏi mẫu>
**Đáp:** <dàn ý câu trả lời mong muốn>

## Trường hợp đặc biệt

- <Tình huống ngoại lệ và cách xử lý>
"""


@dataclass
class DescriptionScore:
    """Chấm mô tả "dùng khi nào" để người soạn sửa trước khi lưu."""

    ok: bool
    level: str            # "tot" | "tam" | "yeu"
    problems: list[str]
    hints: list[str]


def validate_slug(slug: str) -> str:
    slug = (slug or "").strip().lower()
    if not slug:
        raise HTTPException(400, "Thiếu mã kỹ năng (slug)")
    if len(slug) > MAX_SLUG:
        raise HTTPException(400, f"Mã kỹ năng dài {len(slug)} ký tự, tối đa {MAX_SLUG}")
    if not SLUG_RE.match(slug):
        raise HTTPException(400, "Mã kỹ năng chỉ gồm chữ thường không dấu, số và gạch nối; "
                                 "không mở đầu hay kết thúc bằng gạch nối, không có hai gạch liền nhau")
    return slug


def suggest_slug(name: str) -> str:
    """Sinh mã từ tên tiếng Việt: bỏ dấu, thay khoảng trắng bằng gạch nối."""
    table = str.maketrans(
        "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ",
        "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd")
    out = (name or "").strip().lower().translate(table)
    out = re.sub(r"[^a-z0-9]+", "-", out).strip("-")
    out = re.sub(r"-{2,}", "-", out)
    return out[:MAX_SLUG].strip("-") or "ky-nang"


def score_description(description: str) -> DescriptionScore:
    """Mô tả tốt trả lời được hai câu: kỹ năng làm gì, và dùng nó khi nào.

    Chuẩn nói rõ mô tả nên chứa từ khoá giúp agent nhận ra tác vụ liên quan. Ở đây kiểm bằng dấu
    hiệu đơn giản nhưng đủ dùng: độ dài, có nêu tình huống kích hoạt, và có từ khoá nghiệp vụ.
    """
    text = (description or "").strip()
    problems: list[str] = []
    hints: list[str] = []

    if not text:
        return DescriptionScore(False, "yeu", ["Chưa có mô tả"],
                                ["Viết rõ kỹ năng làm gì và dùng khi nào"])
    if len(text) > MAX_DESCRIPTION:
        problems.append(f"Mô tả dài {len(text)} ký tự, tối đa {MAX_DESCRIPTION}")
    if len(text) < MIN_DESCRIPTION:
        problems.append("Mô tả quá ngắn để phân biệt với kỹ năng khác")
        hints.append("Nêu cả việc kỹ năng làm và tình huống dùng nó")

    lowered = text.lower()
    if not any(k in lowered for k in ("khi ", "dùng khi", "lúc ", "trường hợp", "nếu ")):
        hints.append('Thêm vế "Dùng khi…" để mô hình biết lúc nào nên kích hoạt')
    if len(text.split()) < 8:
        problems.append("Mô tả chưa đủ ý")

    level = "tot" if not problems and not hints else ("tam" if not problems else "yeu")
    return DescriptionScore(not problems, level, problems, hints)


def validate_body(body: str) -> str:
    lines = (body or "").splitlines()
    if len(lines) > MAX_BODY_LINES:
        raise HTTPException(400, f"Thân kỹ năng dài {len(lines)} dòng, tối đa {MAX_BODY_LINES}. "
                                 "Tách phần chi tiết thành tài liệu tham chiếu trong kho tri thức.")
    return body or ""


# ---------------------------------------------------------------------------
# Embedding của mô tả: dùng cho cả chọn trước lẫn cảnh báo chồng chéo
# ---------------------------------------------------------------------------

async def embed_description(db: AsyncSession, description: str, *, usage=None,
                            component: str = "skill_embedding") -> list[float] | None:
    """Embed mô tả bằng đúng provider và quy ước 1536 chiều của phần truy hồi.

    ``component`` quyết định dòng token_usage ghi vào đâu. Bộ nhớ cá nhân dùng lại hàm này nhưng
    phải ghi vào thành phần của nó, nếu không trang thống kê sẽ tính chi phí bộ nhớ thành chi phí
    kỹ năng và không ai truy ra được tiền đi đâu.
    """
    from app.services.retrieval import embed_query
    from app.models.ai_provider import AiProvider

    provider = (await db.execute(select(AiProvider).where(
        AiProvider.is_active.is_(True), AiProvider.purpose == "embedding")
        .order_by(AiProvider.created_at).limit(1))).scalar_one_or_none()
    if provider is None:
        return None
    try:
        return await embed_query(description, provider, usage=usage, component=component)
    except Exception:  # thiếu embedding không được chặn việc lưu kỹ năng
        return None


def as_vector(value: Any) -> list[float]:
    """pgvector trả về mảng numpy, mà `arr or []` ném ValueError vì mảng không có giá trị chân lý.
    Mọi chỗ đọc embedding phải đi qua đây."""
    if value is None:
        return []
    return [float(x) for x in value]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


async def find_overlaps(db: AsyncSession, skill: Skill, embedding: list[float] | None) -> list[dict]:
    """Kỹ năng khác trong cùng đơn vị có mô tả gần giống, dễ bị kích hoạt nhầm."""
    if not embedding:
        return []
    rows = (await db.execute(select(Skill).where(
        Skill.workspace_id == skill.workspace_id,
        Skill.id != skill.id,
        Skill.description_embedding.isnot(None)))).scalars().all()
    out = []
    for other in rows:
        score = cosine(embedding, as_vector(other.description_embedding))
        if score >= OVERLAP_THRESHOLD:
            out.append({"id": str(other.id), "name": other.name, "slug": other.slug,
                        "score": round(score, 3)})
    return sorted(out, key=lambda r: -r["score"])[:5]


# ---------------------------------------------------------------------------
# Kỹ năng của một trợ lý
# ---------------------------------------------------------------------------

async def app_skills(db: AsyncSession, app: App, *, channel: str = "staff") -> list[Skill]:
    """Kỹ năng đã công bố mà trợ lý này được dùng trên kênh này, theo thứ tự đã gắn."""
    rows = (await db.execute(
        select(Skill).join(AppSkill, AppSkill.skill_id == Skill.id)
        .where(AppSkill.app_id == app.id, Skill.status == "published")
        .order_by(AppSkill.position))).scalars().all()
    if channel == "customer" or getattr(app, "audience", "staff") == "customer":
        rows = [s for s in rows if s.allow_customer]
    return rows


def catalogue_block(skills: list[Skill]) -> str:
    """Mức 1 của nạp dần: mô hình luôn thấy danh sách này, khoảng 80 token mỗi dòng."""
    if not skills:
        return ""
    lines = ["KỸ NĂNG SẴN CÓ (chỉ đọc toàn văn khi câu hỏi thật sự khớp):"]
    lines += [f"- {s.slug}: {s.description.strip()}" for s in skills]
    return "\n".join(lines)


def skill_block(skill: Skill) -> str:
    """Mức 2: toàn văn kỹ năng, bọc như khối dữ liệu để không bị nhầm là lời người dùng."""
    head = f"{skill.name} (phiên bản {skill.version}"
    head += f", hiệu lực {skill.effective_from})" if skill.effective_from else ")"
    return (f"<<<KỸ NĂNG ĐANG ÁP DỤNG — {head}\n"
            f"{skill.body.strip()}\n"
            ">>>\n"
            "Làm theo kỹ năng trên. Kỹ năng hướng dẫn CÁCH làm; mọi khẳng định về quy định vẫn phải "
            "lấy từ tài liệu trong ngữ cảnh và trích dẫn như bình thường.")


async def preselect(
    db: AsyncSession, app: App, query: str, skills: list[Skill], *, usage=None,
) -> tuple[Skill | None, float]:
    """Chọn trước kỹ năng cho trợ lý không bật agent.

    Trả về (kỹ năng, điểm khớp). Dưới ngưỡng của trợ lý thì trả (None, điểm cao nhất): thà không
    dùng kỹ năng nào còn hơn dùng nhầm.
    """
    usable = [s for s in skills if s.description_embedding is not None]
    if not usable:
        return None, 0.0
    vec = await embed_description(db, query, usage=usage)
    if not vec:
        return None, 0.0
    best, best_score = None, 0.0
    for s in usable:
        score = cosine(vec, as_vector(s.description_embedding))
        if score > best_score:
            best, best_score = s, score
    threshold = float(getattr(app, "skill_match_threshold", 0.32) or 0.32)
    return (best if best_score >= threshold else None), round(best_score, 3)


# ---------------------------------------------------------------------------
# Xuất / nhập theo chuẩn agentskills.io
# ---------------------------------------------------------------------------

def to_skill_md(skill: Skill) -> str:
    """Một kỹ năng thành tệp SKILL.md đúng chuẩn, chạy được trên agent khác."""
    front: dict[str, Any] = {
        "name": skill.slug,
        "description": skill.description.strip(),
        "metadata": {
            "display-name": skill.name,
            "version": skill.version,
            **({"effective-from": skill.effective_from} if skill.effective_from else {}),
        },
    }
    head = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{head}\n---\n\n{skill.body.strip()}\n"


def export_zip(skills: list[Skill]) -> bytes:
    """Nhiều kỹ năng thành một zip, mỗi kỹ năng một thư mục theo đúng bố cục chuẩn."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for s in skills:
            zf.writestr(f"{s.slug}/SKILL.md", to_skill_md(s))
    return buf.getvalue()


def parse_skill_md(text: str) -> dict:
    """Đọc ngược một SKILL.md. Chấp nhận tệp do agent khác sinh ra."""
    if not text.lstrip().startswith("---"):
        raise HTTPException(400, "Tệp SKILL.md phải mở đầu bằng khối YAML giữa hai dòng ---")
    stripped = text.lstrip()
    end = stripped.find("\n---", 3)
    if end == -1:
        raise HTTPException(400, "Không tìm thấy dòng --- đóng khối YAML")
    try:
        front = yaml.safe_load(stripped[3:end]) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(400, f"Khối YAML không hợp lệ: {exc}")
    if not isinstance(front, dict):
        raise HTTPException(400, "Khối YAML phải là một đối tượng")

    slug = validate_slug(str(front.get("name") or ""))
    description = str(front.get("description") or "").strip()
    if not description:
        raise HTTPException(400, "SKILL.md thiếu trường description")
    meta = front.get("metadata") or {}
    meta = meta if isinstance(meta, dict) else {}
    body = stripped[end + 4:].lstrip("-\n")
    return {
        "slug": slug,
        "name": str(meta.get("display-name") or slug),
        "description": description[:MAX_DESCRIPTION],
        "body": validate_body(body.strip()),
        "version": str(meta.get("version") or "v1.0"),
        "effective_from": str(meta.get("effective-from")) if meta.get("effective-from") else None,
    }


def parse_zip(data: bytes) -> list[dict]:
    """Đọc một zip nhiều kỹ năng. Bỏ qua tệp rác, chỉ nhận */SKILL.md."""
    out: list[dict] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.endswith("SKILL.md") and not n.startswith("__")]
            if not names:
                raise HTTPException(400, "Zip không chứa tệp SKILL.md nào")
            for name in sorted(names)[:50]:
                out.append(parse_skill_md(zf.read(name).decode("utf-8")))
    except zipfile.BadZipFile:
        raise HTTPException(400, "Tệp không phải zip hợp lệ")
    return out


def as_uuid_list(raw: Any) -> list[str]:
    """Chuẩn hoá danh sách id gửi từ giao diện: bỏ giá trị rác, giữ thứ tự, không trùng."""
    out: list[str] = []
    for item in raw or []:
        try:
            value = str(uuid.UUID(str(item)))
        except (ValueError, TypeError, AttributeError):
            continue
        if value not in out:
            out.append(value)
    return out
