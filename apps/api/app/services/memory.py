"""Bộ nhớ cá nhân: ba lớp chặn, trích xuất, đọc theo nghĩa, gộp trùng.

Phần khó của tính năng này không phải trích xuất mà là **quyết định cái gì không được nhớ**. Một
trợ lý ngân hàng nhớ nhầm một con số quy định, hay nhớ tên một khách hàng, là sự cố chứ không phải
lỗi nhỏ. Vì vậy bộ lọc ở đây đặt trước mô hình chứ không phải nhờ mô hình ngoan.

Ba lớp, thứ tự từ chắc tới mềm:

1. **Nhãn che PII.** `mask_pii` đã chạy trên mọi tin nhắn trước khi tới đây. Bản ghi nào còn chứa
   một nhãn che là loại ngay, không cần hỏi mô hình. Lớp này là mã, không phải lời dặn.
2. **Loại được phép.** Mô hình phải trả về `category` nằm trong bốn loại. Loại khác là loại bỏ.
3. **Mẫu chặn.** Số tiền, tên riêng đi kèm "khách/anh/chị", từ khoá kết quả nghiệp vụ, và dấu hiệu
   trích dẫn văn bản. Lớp này bắt những gì hai lớp trên lọt.

Chỉ cán bộ và quản trị viên có bộ nhớ. Kênh khách hàng không bao giờ gọi vào đây.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory

logger = logging.getLogger(__name__)

#: Bốn loại được phép nhớ. Mọi thứ ngoài đây bị loại ở lớp 2.
CATEGORIES: dict[str, str] = {
    "trinh_bay": "Cách trình bày câu trả lời người này muốn",
    "vai_tro": "Vai trò và phạm vi công việc của người này",
    "boi_canh": "Việc người này đang theo, nêu theo mã nghiệp vụ",
    "thuat_ngu": "Cách gọi tên riêng người này quen dùng",
}

MAX_TEXT = 240
MAX_PER_PERSON = 60
MAX_NEW_PER_TURN = 2
#: Bối cảnh công việc hết hạn nhanh hơn hẳn: hồ sơ xong rồi mà trợ lý còn nhắc là phiền.
CONTEXT_TTL_DAYS = 30
DEFAULT_TTL_DAYS = 180
#: Trên mức này coi như hai bản ghi nói cùng một chuyện, cập nhật thay vì thêm dòng mới.
DEDUPE_THRESHOLD = 0.88
READ_LIMIT = 5

# --- Lớp 1: nhãn che PII -----------------------------------------------------
# `services/pii.py` thay giá trị nhạy cảm bằng các nhãn trong ngoặc vuông. Bản ghi nhớ mà còn nhãn
# nghĩa là nó đang cố nhớ đúng thứ vừa bị che.
_MASK_LABEL = re.compile(r"\[[A-ZĐÀ-Ỹ][A-ZĐÀ-Ỹ\s_]{2,}\]")

# --- Lớp 3: mẫu chặn ---------------------------------------------------------
_MONEY = re.compile(r"\b\d[\d.,]{5,}\s*(vnd|đ|đồng|usd|tỷ|triệu)\b", re.IGNORECASE)
_PERCENT_RULE = re.compile(r"\b\d{1,3}\s*%|\btối đa\s+\d|\bkhông quá\s+\d", re.IGNORECASE)
# Chữ hoa tiếng Việt liệt kê tường minh: dải "À-Ỹ" trong Unicode lẫn cả chữ thường (á, à, …), nên
# dùng dải là vừa lọt chữ thường vừa sót vài chữ hoa.
_VN_UPPER = ("A-Z" "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬ" "ÈÉẺẼẸÊỀẾỂỄỆ" "ÌÍỈĨỊ"
             "ÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢ" "ÙÚỦŨỤƯỪỨỬỮỰ" "ỲÝỶỸỴ" "Đ")
# Từ dẫn không phân biệt hoa thường vì nó hay đứng đầu câu, nhưng chữ ngay sau phải viết hoa thì
# mới là tên riêng. Nhờ vậy "khách hàng doanh nghiệp FDI" không bị chặn oan.
_NAMED_PERSON = re.compile(
    r"(?i:\b(?:khách hàng|khách|anh|chị|ông|bà|chú|cô))\s+[" + _VN_UPPER + r"]\w+", re.UNICODE)
_OUTCOME = re.compile(
    r"\b(được duyệt|đã duyệt|bị từ chối|từ chối hồ sơ|phê duyệt xong|đã giải ngân|"
    r"nợ xấu|quá hạn thanh toán)\b", re.IGNORECASE)
_DOC_QUOTE = re.compile(r"\b(điều|khoản|thông tư|nghị định|quyết định)\s+\d", re.IGNORECASE)


def rejection_reason(text: str, category: str) -> str | None:
    """Vì sao một bản ghi bị từ chối, hoặc None nếu được phép nhớ.

    Trả về lý do thay vì True/False để bộ kiểm thử và nhật ký nói rõ lớp nào đã chặn.
    """
    value = (text or "").strip()
    if not value:
        return "rỗng"
    if len(value) > MAX_TEXT:
        return f"dài quá {MAX_TEXT} ký tự"
    if category not in CATEGORIES:
        return f"loại '{category}' không nằm trong bốn loại được phép"
    if _MASK_LABEL.search(value):
        return "chứa dữ liệu đã bị che, tức là đang cố nhớ thông tin cá nhân"
    if _MONEY.search(value):
        return "chứa số tiền"
    if _NAMED_PERSON.search(value):
        return "chứa tên người cụ thể"
    if _OUTCOME.search(value):
        return "chứa kết quả nghiệp vụ của một hồ sơ"
    if _DOC_QUOTE.search(value) or _PERCENT_RULE.search(value):
        return "chứa nội dung quy định; thứ đó thuộc về kho tri thức để trích dẫn được"
    return None


def allowed(text: str, category: str) -> bool:
    return rejection_reason(text, category) is None


# ---------------------------------------------------------------------------
# Đọc
# ---------------------------------------------------------------------------

def _owner_clause(employee_id, user_id):
    return Memory.employee_id == employee_id if employee_id else Memory.user_id == user_id


async def load_for(
    db: AsyncSession, *, employee_id=None, user_id=None, query: str = "", provider=None,
    usage=None, limit: int = READ_LIMIT,
) -> list[Memory]:
    """Bản ghi đã ghim, cộng vài bản ghi gần nghĩa nhất với câu hỏi.

    Ghim luôn được nạp vì người dùng đã nói rõ đó là thứ quan trọng; phần còn lại chọn theo nghĩa
    để một người có nhiều bản ghi không làm phình prompt.
    """
    if not employee_id and not user_id:
        return []
    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(Memory).where(
        _owner_clause(employee_id, user_id),
        (Memory.expires_at.is_(None)) | (Memory.expires_at > now),
    ))).scalars().all()
    if not rows:
        return []

    pinned = [m for m in rows if m.pinned]
    rest = [m for m in rows if not m.pinned]
    if not rest or not query:
        return (pinned + rest)[:limit + len(pinned)]

    from app.services.skills import as_vector, cosine

    vec = await _embed(db, query, usage=usage)
    if not vec:
        rest.sort(key=lambda m: m.created_at, reverse=True)
        return pinned + rest[:limit]
    scored = [(cosine(vec, as_vector(m.embedding)), m) for m in rest]
    scored.sort(key=lambda pair: -pair[0])
    return pinned + [m for score, m in scored[:limit] if score > 0.1]


def memory_block(items: list[Memory]) -> str:
    """Khối dữ liệu chèn vào prompt.

    Nói thẳng trong khối rằng đây không phải nguồn về quy định. Đó là ranh giới quan trọng nhất
    của tính năng, nên nó phải nằm ngay cạnh dữ liệu chứ không chỉ nằm trong tài liệu thiết kế.
    """
    if not items:
        return ""
    lines = "\n".join(f"- {m.text}" for m in items)
    return ("<<<ĐIỀU TRỢ LÝ NHỚ VỀ NGƯỜI HỎI (dùng để chọn cách trả lời; "
            "KHÔNG phải nguồn về quy định, mọi khẳng định nghiệp vụ vẫn phải lấy từ tài liệu)\n"
            f"{lines}\n>>>")


async def mark_used(db: AsyncSession, items: list[Memory]) -> None:
    """Bản ghi còn được dùng thì còn sống: gia hạn theo lần dùng cuối."""
    if not items:
        return
    now = datetime.now(timezone.utc)
    for m in items:
        m.last_used_at = now
        if m.expires_at is not None and not m.pinned:
            ttl = CONTEXT_TTL_DAYS if m.category == "boi_canh" else DEFAULT_TTL_DAYS
            m.expires_at = now + timedelta(days=ttl)


# ---------------------------------------------------------------------------
# Ghi
# ---------------------------------------------------------------------------

class MemoryEntryOut(BaseModel):
    """Một bản ghi nhớ mô hình đề xuất.

    Ràng buộc loại bằng `Literal` để mô hình bị chặn ngay tại chỗ sinh, thay vì sinh bừa rồi bị lọc
    sau. Đây là lớp 2 của bộ chặn; hai lớp còn lại vẫn chạy sau đó, vì lược đồ chỉ bảo đảm giá trị
    **nằm trong** danh sách chứ không bảo đảm mô hình chọn **đúng** giá trị, và càng không biết gì
    về dữ liệu khách hàng hay nội dung quy định.
    """

    loai: Literal["trinh_bay", "vai_tro", "boi_canh", "thuat_ngu"] = Field(
        description="trinh_bay: cách trình bày người này muốn. "
                    "vai_tro: vai trò và phạm vi công việc. "
                    "boi_canh: việc đang theo, nêu theo mã nghiệp vụ. "
                    "thuat_ngu: cách gọi tên riêng người này quen dùng.")
    noi_dung: str = Field(max_length=MAX_TEXT,
                          description="Một câu ngắn về NGƯỜI HỎI, ngôi thứ ba. "
                                      "Không nhắc khách hàng, số tiền, kết quả hồ sơ hay nội dung quy định.")


class MemoryExtraction(BaseModel):
    """Kết quả trích xuất. Danh sách rỗng là kết quả bình thường và hay gặp nhất."""

    ghi_nho: list[MemoryEntryOut] = Field(default_factory=list, max_length=MAX_NEW_PER_TURN)


EXTRACT_PROMPT = """Bạn đọc một lượt trao đổi giữa trợ lý và một CÁN BỘ NGÂN HÀNG, và rút ra điều đáng nhớ về **cách làm việc của chính cán bộ đó** để lần sau trả lời hợp hơn.

CHỈ được ghi bốn loại sau:
- trinh_bay: cách trình bày người này muốn. Ví dụ "thích câu trả lời ngắn, có bước đánh số".
- vai_tro: vai trò và phạm vi công việc. Ví dụ "phụ trách khách hàng doanh nghiệp FDI".
- boi_canh: việc đang theo, nêu theo MÃ nghiệp vụ. Ví dụ "đang theo hồ sơ HS2026-0412".
- thuat_ngu: cách gọi tên riêng người này quen dùng. Ví dụ "gọi Khối Vận hành là OPS".

TUYỆT ĐỐI KHÔNG ghi:
- Bất cứ gì về khách hàng: tên, số tài khoản, số tiền, tình trạng hồ sơ của họ.
- Kết quả nghiệp vụ: hồ sơ được duyệt hay bị từ chối.
- Nhận xét về đồng nghiệp.
- Nội dung quy định, con số, tỉ lệ, tên Điều Khoản. Những thứ đó nằm trong tài liệu, không phải bộ nhớ.

Không có gì đáng nhớ thì trả về danh sách rỗng. Đó là kết quả bình thường và hay gặp nhất; đừng cố nghĩ ra.

Trả về ĐÚNG JSON, không thêm chữ nào:
{"ghi_nho": [{"loai": "trinh_bay", "noi_dung": "..."}]}

Mỗi nội dung là một câu ngắn dưới 200 ký tự, viết ở ngôi thứ ba về người hỏi.
Tối đa 2 mục."""


async def _structured_extract(db: AsyncSession, payload: str, *, usage=None) -> list[dict] | None:
    """Trích xuất có ràng buộc lược đồ. Trả về None khi provider không hỗ trợ, để người gọi lùi về
    cách đọc JSON thủ công.

    Dùng ``include_raw=True`` để vẫn lấy được số token mà nhà cung cấp báo: nếu chỉ nhận đối tượng
    đã phân tích thì mất luôn phần đo chi phí.
    """
    from app.models.ai_provider import AiProvider
    from app.services.agent_runtime import build_chat_model
    from app.services.usage import TokenMeter, messages_text, record_usage

    provider = (await db.execute(select(AiProvider).where(
        AiProvider.is_active.is_(True), AiProvider.purpose == "llm")
        .order_by(AiProvider.created_at).limit(1))).scalar_one_or_none()
    if provider is None:
        return None
    model = build_chat_model(provider)
    if model is None:
        return None  # google / anthropic: lùi về đường cũ

    messages = [{"role": "system", "content": EXTRACT_PROMPT}, {"role": "user", "content": payload}]
    try:
        result = await model.with_structured_output(
            MemoryExtraction, include_raw=True).ainvoke(messages)
    except Exception:
        logger.debug("memory: structured output thất bại, lùi về đọc JSON", exc_info=True)
        return None

    raw, parsed = result.get("raw"), result.get("parsed")
    meter = TokenMeter()
    counts = getattr(raw, "usage_metadata", None) or {}
    if counts:
        meter.set(counts.get("input_tokens"), counts.get("output_tokens"))
    await record_usage(usage, component="memory_extract", purpose="llm", provider=provider,
                       meter=meter, prompt_text=messages_text(messages),
                       completion_text=str(parsed) if parsed else "")
    if parsed is None:
        return []
    return [{"loai": e.loai, "noi_dung": e.noi_dung} for e in parsed.ghi_nho]


async def extract(
    db: AsyncSession, question: str, answer: str, *, provider=None, usage=None,
) -> list[dict]:
    """Nhờ mô hình rút bản ghi nhớ, rồi lọc lại bằng ba lớp chặn.

    Chạy trong request chứ không chạy nền, vì giao diện phải báo ngay "đã ghi nhớ gì" kèm nút hoàn
    tác. Người dùng biết trợ lý vừa học gì đúng lúc nó học, và sửa được trong một bấm.
    """
    from app.services.chat import _call_json_model

    payload = (f"Câu hỏi của cán bộ:\n{question[:1500]}\n\n"
               f"Câu trả lời của trợ lý:\n{answer[:1500]}")

    # Lớp 2 ưu tiên ràng buộc lược đồ: mô hình bị chặn ngay tại chỗ sinh nên không còn JSON hỏng.
    # Provider không tương thích OpenAI thì lùi về đọc JSON thủ công, vốn chạy với mọi nhà cung cấp.
    items = await _structured_extract(db, payload, usage=usage)
    if items is None:
        try:
            raw = await _call_json_model(db, EXTRACT_PROMPT, payload, provider=provider,
                                         usage=usage, component="memory_extract")
        except Exception:
            logger.debug("memory: không trích xuất được", exc_info=True)
            return []
        items = raw.get("ghi_nho") if isinstance(raw, dict) else None
    out: list[dict] = []
    for item in (items or [])[:MAX_NEW_PER_TURN]:
        if not isinstance(item, dict):
            continue
        category = str(item.get("loai") or "").strip()
        text = " ".join(str(item.get("noi_dung") or "").split())
        reason = rejection_reason(text, category)
        if reason:
            logger.info("memory: bỏ bản ghi (%s): %s", reason, text[:80])
            continue
        out.append({"category": category, "text": text})
    return out


async def save(
    db: AsyncSession, entries: list[dict], *, employee_id=None, user_id=None, workspace_id=None,
    run_id=None, conversation_id=None, retention_days: int = DEFAULT_TTL_DAYS, usage=None,
) -> list[Memory]:
    """Lưu bản ghi mới, gộp vào bản ghi cũ nếu trùng nghĩa.

    Gộp thay vì thêm để bộ nhớ không phình: một người nói "ngắn gọn thôi" năm lần thì vẫn chỉ có
    một dòng.
    """
    if not entries or (not employee_id and not user_id):
        return []
    from app.services.skills import as_vector, cosine

    existing = (await db.execute(select(Memory).where(
        _owner_clause(employee_id, user_id)))).scalars().all()
    if len(existing) >= MAX_PER_PERSON:
        # Đủ trần: bỏ bản ghi cũ nhất chưa ghim để chỗ cho cái mới.
        oldest = sorted([m for m in existing if not m.pinned],
                        key=lambda m: m.last_used_at or m.created_at)[:len(entries)]
        for m in oldest:
            await db.delete(m)
        existing = [m for m in existing if m not in oldest]

    now = datetime.now(timezone.utc)
    saved: list[Memory] = []
    for entry in entries:
        vec = await _embed(db, entry["text"], usage=usage)
        merged = None
        if vec:
            for m in existing:
                if m.category == entry["category"] and cosine(vec, as_vector(m.embedding)) >= DEDUPE_THRESHOLD:
                    merged = m
                    break
        ttl = CONTEXT_TTL_DAYS if entry["category"] == "boi_canh" else retention_days
        if merged is not None:
            merged.text = entry["text"]
            merged.embedding = vec
            merged.last_used_at = now
            merged.expires_at = now + timedelta(days=ttl)
            saved.append(merged)
            continue
        row = Memory(
            employee_id=employee_id, user_id=user_id, workspace_id=workspace_id,
            category=entry["category"], text=entry["text"], embedding=vec,
            source_run_id=run_id, source_conversation_id=conversation_id,
            last_used_at=now, expires_at=now + timedelta(days=ttl),
        )
        db.add(row)
        existing.append(row)
        saved.append(row)
    await db.flush()
    return saved


async def purge_expired(db: AsyncSession) -> int:
    """Bộ lập lịch gọi mỗi vòng, giống việc dọn tệp báo cáo hết hạn."""
    now = datetime.now(timezone.utc)
    result = await db.execute(delete(Memory).where(
        Memory.expires_at.isnot(None), Memory.expires_at < now, Memory.pinned.is_(False)))
    return result.rowcount or 0


async def forget_employee(db: AsyncSession, employee_id) -> int:
    """Cán bộ nghỉ việc thì bộ nhớ đi theo. Quyền xoá của luật, và không để lại dữ liệu mồ côi."""
    result = await db.execute(delete(Memory).where(Memory.employee_id == employee_id))
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------

async def _embed(db: AsyncSession, text: str, *, usage=None) -> list[float] | None:
    from app.services.skills import embed_description

    return await embed_description(db, text, usage=usage, component="memory_embedding")


def to_dict(m: Memory) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "category": m.category,
        "category_label": CATEGORIES.get(m.category, m.category),
        "text": m.text,
        "pinned": m.pinned,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "last_used_at": m.last_used_at.isoformat() if m.last_used_at else None,
        "expires_at": m.expires_at.isoformat() if m.expires_at else None,
        "conversation_id": str(m.source_conversation_id) if m.source_conversation_id else None,
    }


def parse_json_block(text: str) -> dict | None:
    """Mô hình hay bọc JSON trong ```json. Lấy khối JSON đầu tiên tìm được."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def as_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None
