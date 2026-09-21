"""Bộ kiểm `data` của node luồng xử lý.

Bài quan trọng nhất ở đây là `test_seed_graphs_pass`: mọi luồng mẫu trong `seed_demo` phải qua
được bộ kiểm. Đó là lưới an toàn chống `NODE_SPECS` trôi lệch khỏi `workflow_runtime`. Nếu ai đó
thêm một trường bắt buộc mà runtime không thật sự cần, hoặc đổi tên trường trong runtime mà quên
sửa đặc tả, bài này đỏ ngay.
"""

import uuid

import pytest

from app.services.workflow_schema import (
    NODE_SPECS,
    prompt_block,
    validate_branches,
    validate_node_data,
)
from app.services.workflow_validator import ValidationError, validate_graph

DS = str(uuid.uuid4())
TOOL = str(uuid.uuid4())


def graph(*nodes: dict, edges: list | None = None) -> dict:
    return {"nodes": list(nodes), "edges": edges or []}


def node(ntype: str, **data) -> dict:
    return {"id": ntype, "type": ntype, "data": data}


# --------------------------------------------------------------------------- luồng mẫu thật

def test_seed_graphs_pass():
    """Luồng mẫu trong seed_demo là luồng đang chạy thật, nên phải hợp lệ tuyệt đối."""
    from app.seed_demo import (
        _complaint_report_graph, _incident_graph, _rb_report_graph, _report_graph, _router_graph,
        _ttqt_report_graph, _xlsx_report_graph,
    )

    ds1, ds2, tool = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ids, tools = {str(ds1), str(ds2)}, {str(tool)}
    for name, g in [
        ("router", _router_graph(ds1, ds2)),
        ("report docx", _report_graph(ds1, tool, "reports/mau.docx")),
        ("report không template", _report_graph(ds1, tool, None)),
        ("xlsx", _xlsx_report_graph(tool)),
        ("ttqt", _ttqt_report_graph(tool, tool, ds1)),
        ("rb", _rb_report_graph(tool)),
        ("khiếu nại", _complaint_report_graph(tool, tool, ds1)),
        ("sự cố", _incident_graph(ds1)),
    ]:
        validate_graph(g)
        validate_branches(g)
        validate_node_data(g, dataset_ids=ids, tool_ids=tools)


# --------------------------------------------------------------------------- trường bắt buộc

def test_retrieve_needs_datasets():
    with pytest.raises(ValidationError, match="dataset_ids"):
        validate_node_data(graph(node("retrieve")))


def test_parameter_extract_needs_schema():
    with pytest.raises(ValidationError, match="schema"):
        validate_node_data(graph(node("parameter_extract")))


def test_tool_call_needs_tool_id():
    with pytest.raises(ValidationError, match="tool_id"):
        validate_node_data(graph(node("tool_call", alias="x")))


def test_code_execute_needs_code():
    with pytest.raises(ValidationError, match="code"):
        validate_node_data(graph(node("code_execute")))


# --------------------------------------------------------------------------- kiểu và giá trị

def test_top_k_must_be_int():
    with pytest.raises(ValidationError, match="top_k"):
        validate_node_data(graph(node("retrieve", dataset_ids=[DS], top_k="năm")))


def test_parameter_extract_schema_is_flat_map_not_json_schema():
    """Runtime đọc {tên: mô tả}. Đưa JSON Schema vào là node chạy nhưng rút sai."""
    with pytest.raises(ValidationError, match="schema"):
        validate_node_data(graph(node("parameter_extract",
                                      schema={"type": "object", "properties": {"a": {"type": "string"}}})))
    validate_node_data(graph(node("parameter_extract", schema={"y_dinh": "tin_dung hoặc van_hanh"})))


def test_operator_must_be_known():
    with pytest.raises(ValidationError, match="operator"):
        validate_node_data(graph(node("if_else", variable="x", operator="gt", value="1")))


def test_equals_requires_a_value():
    with pytest.raises(ValidationError, match="value"):
        validate_node_data(graph(node("if_else", variable="x", operator="equals")))
    validate_node_data(graph(node("if_else", variable="x", operator="exists")))


def test_render_document_format_drives_required_fields():
    with pytest.raises(ValidationError, match="sheets"):
        validate_node_data(graph(node("render_document", format="xlsx")))
    with pytest.raises(ValidationError, match="template_key"):
        validate_node_data(graph(node("render_document", format="docx")))
    validate_node_data(graph(node("render_document", format="xlsx", sheets=[{"name": "A"}])))


def test_unknown_format_rejected():
    with pytest.raises(ValidationError, match="format"):
        validate_node_data(graph(node("render_document", format="pdf", template="x")))


# --------------------------------------------------------------------------- đối chiếu id thật

def test_dataset_must_belong_to_the_unit():
    other = str(uuid.uuid4())
    with pytest.raises(ValidationError, match="không thuộc đơn vị"):
        validate_node_data(graph(node("retrieve", dataset_ids=[other])), dataset_ids={DS})
    validate_node_data(graph(node("retrieve", dataset_ids=[DS])), dataset_ids={DS})


def test_tool_must_belong_to_the_unit():
    with pytest.raises(ValidationError, match="không thuộc đơn vị"):
        validate_node_data(graph(node("tool_call", tool_id=str(uuid.uuid4()))), tool_ids={TOOL})


def test_dataset_id_must_look_like_a_uuid():
    with pytest.raises(ValidationError, match="dataset_ids"):
        validate_node_data(graph(node("retrieve", dataset_ids=["kho-tin-dung"])))


# --------------------------------------------------------------------------- rẽ nhánh

def test_branch_needs_exactly_two_edges():
    g = graph(node("if_else", variable="x", operator="exists"), node("answer"),
              edges=[{"source": "if_else", "target": "answer"}])
    with pytest.raises(ValidationError, match="đúng 2"):
        validate_branches(g)


def test_branch_with_two_edges_is_fine():
    g = graph(node("if_else", variable="x", operator="exists"),
              {"id": "a", "type": "answer", "data": {}}, {"id": "b", "type": "answer", "data": {}},
              edges=[{"source": "if_else", "target": "a"}, {"source": "if_else", "target": "b"}])
    validate_branches(g)


# --------------------------------------------------------------------------- khối cho mô hình

def test_prompt_block_covers_every_node_type():
    text = prompt_block()
    for ntype in NODE_SPECS:
        assert f"### {ntype}" in text


def test_prompt_block_marks_required_fields():
    text = prompt_block()
    assert "dataset_ids" in text and "BẮT BUỘC" in text
    # thứ tự cạnh của node rẽ nhánh là chỗ dễ sai nhất, phải nói rõ cho mô hình
    assert "cạnh thứ nhất là nhánh" in text


def test_label_is_allowed_on_every_node():
    for ntype, spec in NODE_SPECS.items():
        assert any(f.name == "label" for f in spec.fields), ntype
