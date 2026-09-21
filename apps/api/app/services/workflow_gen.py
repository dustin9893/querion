"""Khai triển một **danh sách bước phẳng** thành đồ thị React Flow, và ngược lại.

Vì sao tồn tại module này: khi nhờ mô hình soạn luồng, đừng bắt nó xuất thẳng JSON React Flow.
Làm vậy nó phải tự bịa id, giữ id khớp giữa `nodes` và `edges`, đặt toạ độ x/y, và nhớ rằng cạnh
đầu tiên của node rẽ nhánh là nhánh đúng. Mỗi thứ là một chỗ để sai.

Ở đây mô hình chỉ **liệt kê các bước**, máy chủ **vẽ đồ thị**. Việc của mô hình rút từ "dựng một
đồ thị nhất quán" xuống "kể ra các bước theo thứ tự", nên mọi lỗi còn lại đều là lỗi nội dung chứ
không phải lỗi hình thức.

Dạng danh sách bước, khoá tiếng Việt cho khớp văn phong các công cụ khác::

    {
      "ten": "Định tuyến câu hỏi nội bộ",
      "mo_ta": "Phân loại ý định rồi tra đúng kho",
      "buoc": [
        {"loai": "parameter_extract", "schema": {"y_dinh": "tin_dung hoặc van_hanh"}},
        {"loai": "if_else", "variable": "extracted_params.y_dinh", "operator": "equals",
         "value": "tin_dung",
         "neu_dung": [{"loai": "retrieve", "dataset_ids": ["..."], "top_k": 5}],
         "neu_sai":  [{"loai": "retrieve", "dataset_ids": ["..."], "top_k": 5}]},
        {"loai": "compose_prompt", "template": "..."},
        {"loai": "llm_generate", "temperature": 0.2}
      ]
    }

Node `input` và `output` được tự thêm nếu thiếu, vì đó là lỗi mô hình hay quên nhất và nó không
mang thông tin gì.
"""

from __future__ import annotations

from typing import Any

from app.services.workflow_schema import (
    NODE_SPECS,
    validate_branches,
    validate_node_data,
)
from app.services.workflow_validator import ValidationError, validate_graph

MAX_STEPS = 24
COL_WIDTH = 260
LANE_HEIGHT = 150
BASE_Y = 160

_BRANCH_KEYS = ("neu_dung", "neu_sai")
#: khoá điều khiển của danh sách bước, không phải trường `data` của node
_CONTROL_KEYS = {"loai", "nhan", *_BRANCH_KEYS}


# ---------------------------------------------------------------------------
# Bố cục
# ---------------------------------------------------------------------------

class _Layout:
    """Giữ chỗ đã dùng để không bao giờ đặt hai node chồng lên nhau."""

    def __init__(self) -> None:
        self.taken: set[tuple[int, int]] = set()

    def place(self, col: int, preferred_lane: int) -> int:
        lane = preferred_lane
        step = 0
        while (col, lane) in self.taken:
            step += 1
            lane = preferred_lane + step if step % 2 else preferred_lane - step
        self.taken.add((col, lane))
        return lane


# ---------------------------------------------------------------------------
# Danh sách bước -> đồ thị
# ---------------------------------------------------------------------------

def _clean_data(step: dict, spec_type: str, where: str) -> dict:
    """Giữ đúng các trường `data` mà runtime đọc, bỏ mọi thứ mô hình bịa thêm."""
    spec = NODE_SPECS[spec_type]
    allowed = {f.name for f in spec.fields}
    data: dict[str, Any] = {}
    for key, value in step.items():
        if key in _CONTROL_KEYS:
            continue
        if key in allowed:
            data[key] = value
    label = step.get("nhan") or step.get("label")
    data["label"] = str(label) if label else spec.label
    return data


def _expand(
    steps: list[dict],
    *,
    col: int,
    lane: int,
    layout: _Layout,
    ids: dict[str, int],
    nodes: list[dict],
    edges: list[dict],
    labels: dict[str, str],
    where: str,
    depth: int,
    offset: int = 0,
) -> tuple[str | None, list[str], int]:
    """Dựng một chuỗi bước. Trả về (id node đầu, các id node cuối cần nối tiếp, cột kế tiếp).

    ``offset`` bù lại các node input/output tự thêm, để số thứ tự bước trong thông báo lỗi khớp
    với danh sách mà mô hình đã viết ra chứ không lệch đi một.
    """
    entry: str | None = None
    exits: list[str] = []

    for index, step in enumerate(steps, start=1):
        here = f"{where}bước {index + offset}"
        if not isinstance(step, dict):
            raise ValidationError(f"{here}: mỗi bước phải là một đối tượng JSON")
        ntype = str(step.get("loai") or step.get("type") or "").strip()
        if ntype not in NODE_SPECS:
            raise ValidationError(
                f"{here}: 'loai' là '{ntype or 'trống'}', phải là một trong "
                + ", ".join(k for k in NODE_SPECS if k not in ("input", "output")))
        if ntype in ("input", "output") and depth > 0:
            raise ValidationError(f"{here}: không được đặt node '{ntype}' bên trong một nhánh")

        ids[ntype] = ids.get(ntype, 0) + 1
        node_id = f"{ntype}_{ids[ntype]}" if ids[ntype] > 1 else ntype
        labels[node_id] = f"{here} ({NODE_SPECS[ntype].label})"
        placed_lane = layout.place(col, lane)
        nodes.append({
            "id": node_id,
            "type": ntype,
            "position": {"x": col * COL_WIDTH, "y": BASE_Y + placed_lane * LANE_HEIGHT},
            "data": _clean_data(step, ntype, here),
        })
        if entry is None:
            entry = node_id
        for src in exits:
            edges.append({"id": f"e-{src}-{node_id}", "source": src, "target": node_id})

        if ntype == "if_else":
            branches: list[tuple[str, list[dict]]] = []
            for key, side in zip(_BRANCH_KEYS, ("nhánh đúng", "nhánh sai")):
                raw = step.get(key)
                if not isinstance(raw, list) or not raw:
                    raise ValidationError(
                        f"{here}: node rẽ nhánh phải có '{key}' là danh sách ít nhất một bước "
                        f"({side}). Nhánh rỗng khiến luồng dừng giữa chừng mà không báo gì.")
                branches.append((key, raw))

            next_col = col + 1
            branch_exits: list[str] = []
            # Thứ tự quan trọng: cạnh ra thứ nhất là nhánh đúng, thứ hai là nhánh sai.
            for lane_offset, (key, raw) in zip((-1, 1), branches):
                side = "nhánh đúng" if key == "neu_dung" else "nhánh sai"
                b_entry, b_exits, b_col = _expand(
                    raw, col=col + 1, lane=lane + lane_offset, layout=layout, ids=ids,
                    nodes=nodes, edges=edges, labels=labels,
                    where=f"{here} → {side} → ", depth=depth + 1)
                edges.append({"id": f"e-{node_id}-{b_entry}", "source": node_id, "target": b_entry,
                              "sourceHandle": "true" if key == "neu_dung" else "false"})
                branch_exits.extend(b_exits)
                next_col = max(next_col, b_col)
            exits = branch_exits
            col = next_col
        else:
            exits = [node_id]
            col += 1

    return entry, exits, col


def steps_to_graph(
    spec: dict[str, Any],
    *,
    dataset_ids: set[str] | None = None,
    tool_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Danh sách bước -> đồ thị React Flow đã kiểm đầy đủ.

    Ném `ValidationError` với thông báo chỉ đúng số thứ tự bước, để vòng sửa lỗi đưa lại cho mô
    hình biết phải sửa chỗ nào.
    """
    if not isinstance(spec, dict):
        raise ValidationError("Đặc tả luồng phải là một đối tượng JSON")
    steps = spec.get("buoc") or spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValidationError("Thiếu 'buoc': danh sách các bước của luồng")

    flat = _count_steps(steps)
    if flat > MAX_STEPS:
        raise ValidationError(f"Luồng có {flat} bước, tối đa {MAX_STEPS}. Hãy rút gọn.")

    body = [s for s in steps if isinstance(s, dict)]
    # input/output không mang thông tin, mô hình hay quên — tự thêm thay vì bắt nó sửa.
    offset = 0
    if not body or body[0].get("loai") != "input":
        body = [{"loai": "input"}, *body]
        offset = -1
    if body[-1].get("loai") != "output":
        body = [*body, {"loai": "output"}]

    nodes: list[dict] = []
    edges: list[dict] = []
    labels: dict[str, str] = {}
    _expand(body, col=0, lane=0, layout=_Layout(), ids={}, nodes=nodes, edges=edges,
            labels=labels, where="", depth=0, offset=offset)

    graph = {"nodes": nodes, "edges": edges}
    validate_graph(graph)
    validate_branches(graph)
    validate_node_data(graph, dataset_ids=dataset_ids, tool_ids=tool_ids, labels=labels)
    return graph


def _count_steps(steps: list) -> int:
    total = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        total += 1
        for key in _BRANCH_KEYS:
            branch = step.get(key)
            if isinstance(branch, list):
                total += _count_steps(branch)
    return total


# ---------------------------------------------------------------------------
# Đồ thị -> danh sách bước (để sửa một luồng đang có)
# ---------------------------------------------------------------------------

def graph_to_steps(graph_json: dict[str, Any]) -> dict[str, Any]:
    """Dịch ngược một đồ thị về danh sách bước, để mô hình đọc và sửa.

    Trả về ``{"buoc": [...]}``. Với đồ thị không biểu diễn được bằng danh sách bước, ví dụ rẽ
    nhánh mà hai nhánh không gặp lại nhau, trả thêm ``"khong_day_du": true`` và phần dịch được
    tới đó. Người gọi nên nói rõ với mô hình là chỉ sửa những gì thấy.
    """
    nodes = {n["id"]: n for n in graph_json.get("nodes") or [] if n.get("id")}
    outgoing: dict[str, list[str]] = {nid: [] for nid in nodes}
    for edge in graph_json.get("edges") or []:
        if edge.get("source") in outgoing and edge.get("target") in nodes:
            outgoing[edge["source"]].append(edge["target"])

    start = next((nid for nid, n in nodes.items() if n.get("type") == "input"), None)
    if start is None:
        return {"buoc": [], "khong_day_du": True}

    truncated = {"value": False}

    def walk(node_id: str | None, stop: str | None, seen: set[str]) -> list[dict]:
        out: list[dict] = []
        current = node_id
        while current and current != stop:
            if current in seen:
                truncated["value"] = True
                break
            seen.add(current)
            node = nodes.get(current)
            if node is None:
                truncated["value"] = True
                break
            ntype = node.get("type")
            data = dict(node.get("data") or {})
            step: dict[str, Any] = {"loai": ntype}
            label = data.pop("label", None)
            for key, value in data.items():
                step[key] = value
            if label:
                step["nhan"] = label

            targets = outgoing.get(current, [])
            if ntype == "if_else" and len(targets) == 2:
                merge = _first_common(outgoing, targets[0], targets[1])
                step["neu_dung"] = walk(targets[0], merge, set(seen))
                step["neu_sai"] = walk(targets[1], merge, set(seen))
                if merge is None:
                    truncated["value"] = True
                if ntype not in ("input", "output"):
                    out.append(step)
                current = merge
                continue

            if ntype not in ("input", "output"):
                out.append(step)
            current = targets[0] if len(targets) == 1 else None
            if len(targets) > 1:
                truncated["value"] = True
        return out

    steps = walk(start, None, set())
    result: dict[str, Any] = {"buoc": steps}
    if truncated["value"]:
        result["khong_day_du"] = True
    return result


def _first_common(outgoing: dict[str, list[str]], a: str, b: str) -> str | None:
    """Node đầu tiên mà hai nhánh gặp lại nhau, hoặc None nếu chúng không gặp."""
    def reachable(start: str) -> list[str]:
        order: list[str] = []
        seen = {start}
        queue = [start]
        while queue:
            cur = queue.pop(0)
            order.append(cur)
            for nxt in outgoing.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return order

    from_b = set(reachable(b))
    for node in reachable(a):
        if node in from_b:
            return node
    return None
