"""Đặc tả các node của luồng xử lý — nguồn sự thật duy nhất.

`workflow_validator.validate_graph` chỉ kiểm **cấu trúc** đồ thị: kiểu node hợp lệ, đúng một
input và một output, không chu trình, có đường đi. Nó không đọc `node["data"]` một dòng nào, nên
một node `retrieve` thiếu `dataset_ids` hay `tool_call` trỏ vào công cụ không tồn tại vẫn qua
được rồi chết lúc chạy.

Module này bù chỗ đó. Mỗi loại node khai báo các trường `data` nó thật sự đọc trong
`workflow_runtime.py`, kiểu, giá trị mặc định và bắt buộc hay không. Một bản khai báo dùng cho
bốn việc, nên không thể trôi lệch:

1. `validate_node_data()` — kiểm mọi luồng, dù do người vẽ tay hay do trợ lý sinh ra.
2. `prompt_block()` — khối đặc tả chèn vào prompt khi nhờ mô hình soạn luồng.
3. Bảng thuộc tính trên canvas, khi cần.
4. Tài liệu cẩm nang vận hành.

Khi thêm một loại node mới vào runtime, thêm `NodeSpec` ở đây trong cùng một lần sửa.
`tests/test_workflow_schema.py` bắt buộc mọi luồng mẫu trong `seed_demo` phải qua được bộ kiểm,
đó là lưới an toàn chống đặc tả lệch khỏi runtime.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.services.workflow_validator import ValidationError

# ---------------------------------------------------------------------------
# Kiểu trường
# ---------------------------------------------------------------------------

#: tên kiểu -> (mô tả tiếng Việt, hàm kiểm)
_CHECKS: dict[str, Any] = {
    "string": lambda v: isinstance(v, str),
    "text": lambda v: isinstance(v, str),
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "map_str": lambda v: isinstance(v, dict) and all(isinstance(k, str) and isinstance(x, str) for k, x in v.items()),
    "id": lambda v: _is_uuid(v),
    "id_list": lambda v: isinstance(v, list) and bool(v) and all(_is_uuid(x) for x in v),
}

_TYPE_LABEL = {
    "string": "chuỗi", "text": "chuỗi dài", "int": "số nguyên", "number": "số",
    "bool": "true/false", "object": "đối tượng JSON", "array": "mảng",
    "map_str": "đối tượng {tên: mô tả}", "id": "UUID dạng chuỗi", "id_list": "mảng UUID dạng chuỗi",
}


def _is_uuid(value: Any) -> bool:
    if isinstance(value, uuid.UUID):
        return True
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    description: str
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] | None = None
    #: chỉ bắt buộc khi trường khác mang một trong các giá trị này, dạng ("format", ("xlsx",))
    required_when: tuple[str, tuple[str, ...]] | None = None


@dataclass(frozen=True)
class NodeSpec:
    type: str
    label: str
    summary: str
    fields: tuple[Field, ...] = ()
    notes: str = ""
    #: node này chỉ dùng cho luồng báo cáo
    report_only: bool = False


# Mọi node đều được mang `label`: nhãn hiển thị trên canvas, runtime không đọc.
_COMMON = Field("label", "string", "Nhãn hiển thị trên canvas, không ảnh hưởng lúc chạy")


NODE_SPECS: dict[str, NodeSpec] = {
    "input": NodeSpec(
        type="input",
        label="Đầu vào",
        summary="Điểm bắt đầu. Mỗi luồng có đúng một node này.",
        fields=(
            _COMMON,
            Field("fields", "array", "Chỉ dùng cho luồng báo cáo: danh sách trường người dùng phải điền, "
                                     "mỗi phần tử có name, label, type, required, options"),
        ),
    ),
    "retrieve": NodeSpec(
        type="retrieve",
        label="Tra kho tri thức",
        summary="Tìm các đoạn văn bản liên quan tới câu hỏi trong một hoặc nhiều kho tri thức. "
                "Kết quả vào ngữ cảnh và trở thành trích dẫn của câu trả lời.",
        fields=(
            _COMMON,
            Field("dataset_ids", "id_list", "Các kho tri thức cần tra, phải là id có thật của đúng đơn vị này",
                  required=True),
            Field("top_k", "int", "Số đoạn lấy về", default=5),
        ),
        notes="Không có dataset_ids thì node chạy nhưng không tra gì, câu trả lời sẽ không có trích dẫn.",
    ),
    "compose_prompt": NodeSpec(
        type="compose_prompt",
        label="Soạn prompt",
        summary="Dựng bộ tin nhắn gửi cho mô hình từ một mẫu văn bản.",
        fields=(
            _COMMON,
            Field("template", "text",
                  "Mẫu prompt. Các chỗ thay thế: {{query}} câu hỏi, {{context}} đoạn đã tra được, "
                  "{{tool_results}} kết quả công cụ, {{answer}} câu trả lời hiện có, {{inputs.<tên>}} giá trị người dùng nhập",
                  default="{{query}}"),
            Field("system_prompt", "text", "Nội dung thay vào chỗ {{system_prompt}} trong mẫu"),
        ),
        notes="Đặt sau node tra kho thì {{context}} mới có nội dung.",
    ),
    "llm_generate": NodeSpec(
        type="llm_generate",
        label="Sinh câu trả lời",
        summary="Gọi mô hình ngôn ngữ với bộ tin nhắn do node soạn prompt dựng ra.",
        fields=(
            _COMMON,
            Field("model", "string", "Tên model, bỏ trống thì dùng model đang bật trong Cài đặt AI"),
            Field("temperature", "number", "Độ sáng tạo, càng thấp càng bám tài liệu", default=0.7),
            Field("max_tokens", "int", "Giới hạn độ dài câu trả lời", default=4096),
        ),
        notes="Với câu trả lời nghiệp vụ nên để temperature từ 0.1 đến 0.3.",
    ),
    "parameter_extract": NodeSpec(
        type="parameter_extract",
        label="Trích tham số",
        summary="Nhờ mô hình rút các trường có cấu trúc ra khỏi câu hỏi. Kết quả nằm ở "
                "extracted_params.<tên trường> và dùng được cho node rẽ nhánh.",
        fields=(
            _COMMON,
            Field("schema", "map_str",
                  "Đối tượng phẳng {tên trường: mô tả cách rút}. KHÔNG phải JSON Schema. "
                  'Ví dụ {"y_dinh": "Phân loại vào đúng một giá trị: tin_dung hoặc van_hanh"}',
                  required=True),
        ),
        notes="Mô tả càng nêu rõ tập giá trị cho phép thì kết quả càng ổn định.",
    ),
    "if_else": NodeSpec(
        type="if_else",
        label="Rẽ nhánh",
        summary="So sánh một giá trị trong trạng thái rồi đi theo một trong hai nhánh.",
        fields=(
            _COMMON,
            Field("variable", "string",
                  "Đường dẫn tới giá trị cần so, ví dụ extracted_params.y_dinh hoặc inputs.thang",
                  required=True),
            Field("operator", "string", "Phép so sánh", default="exists",
                  choices=("exists", "not_empty", "equals", "contains")),
            Field("value", "string", "Giá trị đem so, dùng với equals và contains",
                  required_when=("operator", ("equals", "contains"))),
        ),
        notes="Node này phải có đúng hai cạnh ra. Runtime đọc THỨ TỰ CẠNH: cạnh thứ nhất là nhánh "
              "đúng, cạnh thứ hai là nhánh sai. Thuộc tính sourceHandle chỉ để hiển thị.",
    ),
    "http_request": NodeSpec(
        type="http_request",
        label="Gọi HTTP",
        summary="Gọi một API ngoài. Kết quả nằm ở http_response.",
        fields=(
            _COMMON,
            Field("url", "string", "Địa chỉ đầy đủ, có thể chứa {{query}} và {{inputs.<tên>}}", required=True),
            Field("method", "string", "Phương thức", default="POST",
                  choices=("GET", "POST", "PUT", "PATCH", "DELETE")),
            Field("headers", "object", "Header gửi kèm"),
            Field("body_template", "text", "Thân yêu cầu dạng chuỗi, thường là JSON"),
        ),
        notes="Bị bộ chặn SSRF kiểm. Muốn gọi hệ thống nội bộ thì host phải nằm trong "
              "TOOL_INTERNAL_ALLOWLIST. Cần khoá bí mật thì dùng node gọi công cụ thay vì node này.",
    ),
    "tool_call": NodeSpec(
        type="tool_call",
        label="Gọi công cụ",
        summary="Chạy một công cụ đã đăng ký của đơn vị. Kết quả nằm ở tool_results.<alias>.",
        fields=(
            _COMMON,
            Field("tool_id", "id", "Id công cụ trong sổ đăng ký, phải là công cụ đơn vị này dùng được",
                  required=True),
            Field("mcp_tool", "string", "Khi công cụ là một MCP server: tên tool cụ thể trên server đó"),
            Field("args", "object", "Tham số truyền cho công cụ, giá trị có thể chứa {{inputs.<tên>}}"),
            Field("alias", "string", "Tên chỗ chứa kết quả", default="ket_qua"),
        ),
        notes="Công cụ cần duyệt thao tác bị từ chối ở đây, vì luồng chạy nền không có ai bấm duyệt.",
    ),
    "render_document": NodeSpec(
        type="render_document",
        label="Xuất tài liệu",
        summary="Tạo tệp kết quả và lưu lại thành một tệp tải về được.",
        fields=(
            _COMMON,
            Field("format", "string", "Định dạng tệp", default="markdown",
                  choices=("markdown", "docx", "xlsx")),
            Field("title", "string", "Tiêu đề tài liệu", default="Báo cáo"),
            Field("filename", "string", "Tên tệp, bỏ trống thì lấy theo tiêu đề"),
            Field("template", "text", "Mẫu Markdown, dùng khi format là markdown",
                  required_when=("format", ("markdown",))),
            Field("template_key", "string", "Khoá tệp mẫu .docx đã tải lên, dùng khi format là docx",
                  required_when=("format", ("docx",))),
            Field("sheets", "array", "Đặc tả các sheet, dùng khi format là xlsx: mỗi sheet có name, title, rows "
                                     "(thường là {{tool_results.<alias>.<danh_sách>}}), columns [{header, field, "
                                     "format money|int|number|percent, total}], summary, và charts tuỳ chọn "
                                     "[{type bar|bar_h|line|pie, title, category_field, series [{field, name}]}] "
                                     "vẽ ngay trong sheet từ các cột đã khai",
                  required_when=("format", ("xlsx",))),
            Field("vars", "object", "Ánh xạ {tên ngắn trong mẫu: đường dẫn trong trạng thái}"),
            Field("kind", "string", "Phân loại tệp", default="report"),
            Field("audience", "string", "Để staff thì tệp hiện trong Báo cáo của tôi bên cổng cán bộ",
                  choices=("admin", "staff")),
            Field("retention_days", "int", "Số ngày giữ tệp", default=30),
            Field("set_answer", "bool", "Đưa nội dung tệp vào câu trả lời", default=True),
        ),
        report_only=True,
    ),
    "answer": NodeSpec(
        type="answer",
        label="Trả lời",
        summary="Chốt câu trả lời cuối. Bỏ trống mẫu thì giữ nguyên câu trả lời của node trước.",
        fields=(
            _COMMON,
            Field("template", "text",
                  "Mẫu câu trả lời. Chỗ thay thế: {{answer}}, {{query}}, {{<tên tham số đã trích>}}, {{http_status}}"),
        ),
    ),
    "code_execute": NodeSpec(
        type="code_execute",
        label="Chạy mã Python",
        summary="Chạy một đoạn Python ngắn để biến đổi dữ liệu.",
        fields=(
            _COMMON,
            Field("code", "text", "Mã Python", required=True),
        ),
        notes="Mặc định TẮT bằng biến môi trường ENABLE_CODE_EXECUTE và không phải sandbox thật. "
              "Tránh dùng, chọn node gọi công cụ nếu được.",
    ),
    "output": NodeSpec(
        type="output",
        label="Kết thúc",
        summary="Điểm kết thúc. Mỗi luồng có đúng một node này.",
        fields=(_COMMON,),
    ),
}

#: các node chỉ có nghĩa trong luồng báo cáo
REPORT_ONLY = {t for t, s in NODE_SPECS.items() if s.report_only}


# ---------------------------------------------------------------------------
# Kiểm dữ liệu node
# ---------------------------------------------------------------------------

def validate_node_data(
    graph_json: dict[str, Any],
    *,
    dataset_ids: set[str] | None = None,
    tool_ids: set[str] | None = None,
    where: str = "Node",
    labels: dict[str, str] | None = None,
) -> None:
    """Kiểm `data` của từng node theo `NODE_SPECS`. Ném `ValidationError` ở lỗi đầu tiên.

    `dataset_ids` và `tool_ids` là các id đơn vị hiện có. Truyền vào thì node trỏ sang id không
    tồn tại sẽ bị bắt ngay, thay vì chết lúc chạy. Bỏ trống thì chỉ kiểm định dạng.

    `labels` ánh xạ id node sang cách gọi mà người đọc thông báo nhận ra được. Khi luồng do mô
    hình soạn, đó là số thứ tự bước nó đã viết; nói "Node 'if_else_2'" thì mô hình không biết
    sửa chỗ nào vì id đó do máy chủ đặt ra.
    """
    for index, node in enumerate(graph_json.get("nodes") or []):
        ntype = node.get("type")
        spec = NODE_SPECS.get(ntype)
        if spec is None:
            continue  # kiểu node lạ đã do validate_graph bắt
        data = node.get("data") or {}
        if not isinstance(data, dict):
            raise ValidationError(f"{where} '{node.get('id', index)}': 'data' phải là đối tượng")
        nid = str(node.get("id", index))
        label = (labels or {}).get(nid) or f"{where} '{nid}' ({spec.label})"

        for f in spec.fields:
            present = f.name in data and data[f.name] not in (None, "")
            if not present:
                if f.required:
                    raise ValidationError(f"{label}: thiếu trường bắt buộc '{f.name}' — {f.description}")
                if f.required_when:
                    other, values = f.required_when
                    current = str(data.get(other) or next(
                        (o.default for o in spec.fields if o.name == other), "") or "").lower()
                    if current in values:
                        raise ValidationError(
                            f"{label}: '{other}' là '{current}' nên bắt buộc phải có '{f.name}'")
                continue

            value = data[f.name]
            if not _CHECKS[f.type](value):
                raise ValidationError(
                    f"{label}: trường '{f.name}' phải là {_TYPE_LABEL[f.type]}, đang nhận "
                    f"{type(value).__name__}")
            if f.choices and str(value) not in f.choices:
                raise ValidationError(
                    f"{label}: '{f.name}' phải là một trong {', '.join(f.choices)}, đang nhận '{value}'")

        if dataset_ids is not None and ntype == "retrieve":
            for did in data.get("dataset_ids") or []:
                if str(did) not in dataset_ids:
                    raise ValidationError(
                        f"{label}: kho tri thức '{did}' không thuộc đơn vị này hoặc không tồn tại")
        if tool_ids is not None and ntype == "tool_call":
            tid = data.get("tool_id")
            if tid and str(tid) not in tool_ids:
                raise ValidationError(
                    f"{label}: công cụ '{tid}' không thuộc đơn vị này hoặc không dùng được")


def validate_branches(graph_json: dict[str, Any]) -> None:
    """Node rẽ nhánh phải có đúng hai cạnh ra.

    `validate_graph` chỉ chặn quá hai. Một node rẽ nhánh có một cạnh thì nhánh sai rơi vào hư
    không và luồng dừng giữa chừng mà không báo gì.
    """
    out: dict[str, int] = {}
    for edge in graph_json.get("edges") or []:
        src = edge.get("source")
        if src:
            out[src] = out.get(src, 0) + 1
    for node in graph_json.get("nodes") or []:
        if node.get("type") == "if_else" and out.get(node.get("id"), 0) != 2:
            raise ValidationError(
                f"Node rẽ nhánh '{node.get('id')}' có {out.get(node.get('id'), 0)} cạnh ra, phải đúng 2 "
                "(cạnh thứ nhất là nhánh đúng, cạnh thứ hai là nhánh sai)")


# ---------------------------------------------------------------------------
# Khối đặc tả cho mô hình
# ---------------------------------------------------------------------------

def prompt_block(*, include_report_nodes: bool = True) -> str:
    """Đặc tả node dạng văn bản gọn để chèn vào prompt.

    Cố tình chèn thẳng chứ không để RAG tìm: schema phải chính xác từng trường, mà truy hồi chỉ
    trả về đoạn gần đúng. Thiếu một trường là luồng sinh ra chạy lệch mà không ai biết.
    """
    lines: list[str] = []
    for spec in NODE_SPECS.values():
        if spec.report_only and not include_report_nodes:
            continue
        lines.append(f"### {spec.type} — {spec.label}")
        lines.append(spec.summary)
        for f in spec.fields:
            if f.name == "label":
                continue
            bits = [f"  - {f.name} ({_TYPE_LABEL[f.type]})"]
            if f.required:
                bits.append("BẮT BUỘC")
            elif f.required_when:
                bits.append(f"bắt buộc khi {f.required_when[0]} thuộc {'/'.join(f.required_when[1])}")
            if f.default is not None:
                bits.append(f"mặc định {f.default!r}")
            if f.choices:
                bits.append("một trong: " + ", ".join(f.choices))
            lines.append(" · ".join(bits) + f" — {f.description}")
        if spec.notes:
            lines.append(f"  Lưu ý: {spec.notes}")
        lines.append("")
    return "\n".join(lines).strip()
