"""Công cụ `kich_hoat_ky_nang`: mức 2 của nạp dần, cho trợ lý có agent.

Trợ lý RAG thuần được máy chủ chọn trước kỹ năng, vì nó không có vòng gọi công cụ nào để tự quyết.
Trợ lý có agent thì ngược lại: để mô hình tự gọi đúng như chuẩn Agent Skills mô tả. Nó đã thấy danh
mục tên và mô tả trong system prompt; khi câu hỏi thật sự khớp thì gọi công cụ này để lấy toàn văn.

Công cụ không phải một dòng trong bảng `tools`. Nó dựng từ chính danh sách kỹ năng đã gắn vào trợ
lý, nên không ai gắn nhầm được, và không cần quản trị thêm một bản ghi công cụ cho mỗi kỹ năng.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from app.services.skills import skill_block
from app.services.tools.executor import ToolError

MAX_ACTIVATIONS = 2


def activate_skill_tool(skills: list, sink: list | None):
    """Dựng công cụ cho đúng bộ kỹ năng của một trợ lý.

    ``sink`` nhận bản ghi mỗi lần kích hoạt để router phát chip và ghi nhật ký.
    """
    by_slug = {s.slug: s for s in skills}
    catalogue = "\n".join(f"- {s.slug}: {s.description.strip()}" for s in skills)
    holder: dict[str, Any] = {}
    used: list[str] = []

    schema = {
        "type": "object",
        "properties": {
            "slug": {
                "type": "string",
                "enum": sorted(by_slug),
                "description": "Mã kỹ năng cần đọc, lấy từ danh mục kỹ năng trong hướng dẫn hệ thống",
            },
        },
        "required": ["slug"],
    }

    description = (
        "Đọc toàn văn một kỹ năng nghiệp vụ khi câu hỏi khớp với mô tả của nó. "
        "Gọi TRƯỚC khi trả lời, và chỉ gọi khi thật sự khớp; không khớp thì trả lời bình thường.\n"
        f"Các kỹ năng hiện có:\n{catalogue}"
    )

    async def run(**kwargs: Any) -> str:
        slug = str(kwargs.get("slug") or "").strip()
        skill = by_slug.get(slug)
        if skill is None:
            raise ToolError(f"Không có kỹ năng '{slug}'. Chỉ dùng mã trong danh mục.")
        if slug in used:
            raise ToolError(f"Kỹ năng '{slug}' đã đọc rồi, làm theo nội dung đã có.")
        if len(used) >= MAX_ACTIVATIONS:
            # Đọc nhiều bí kíp cho một câu hỏi là dấu hiệu chọn sai, và làm loãng ngữ cảnh.
            raise ToolError("Đã đọc đủ kỹ năng cho câu hỏi này, hãy trả lời.")
        used.append(slug)
        if sink is not None:
            sink.append({"id": str(skill.id), "slug": skill.slug, "name": skill.name,
                         "version": skill.version, "how": "agent"})
        return skill_block(skill)

    tool = StructuredTool(name="kich_hoat_ky_nang", description=description, args_schema=schema,
                          coroutine=run, func=None, handle_tool_error=True)
    return tool, holder
