"""Khai triển danh sách bước thành đồ thị React Flow.

Đây là chỗ đỡ cho mô hình. Mọi thứ dễ sai khi sinh đồ thị — id trùng, cạnh lệch, node chồng nhau,
nhánh đúng sai đảo chỗ — đều là việc của máy chủ, nên phải có bài kiểm cho từng cái.
"""

import uuid

import pytest

from app.services.workflow_gen import MAX_STEPS, graph_to_steps, steps_to_graph
from app.services.workflow_validator import ValidationError

DS1 = str(uuid.uuid4())
DS2 = str(uuid.uuid4())
IDS = {DS1, DS2}


def types_of(graph: dict) -> list[str]:
    return [n["type"] for n in graph["nodes"]]


def positions(graph: dict) -> list[tuple[int, int]]:
    return [(n["position"]["x"], n["position"]["y"]) for n in graph["nodes"]]


# --------------------------------------------------------------------------- cơ bản

def test_input_and_output_are_added():
    """Mô hình hay quên hai node này và chúng không mang thông tin gì, nên máy chủ tự thêm."""
    g = steps_to_graph({"buoc": [{"loai": "answer"}]})
    assert types_of(g) == ["input", "answer", "output"]


def test_existing_input_is_not_duplicated():
    g = steps_to_graph({"buoc": [{"loai": "input"}, {"loai": "answer"}, {"loai": "output"}]})
    assert types_of(g).count("input") == 1
    assert types_of(g).count("output") == 1


def test_linear_chain_is_fully_connected():
    g = steps_to_graph({"buoc": [
        {"loai": "retrieve", "dataset_ids": [DS1]},
        {"loai": "compose_prompt", "template": "{{context}}"},
        {"loai": "llm_generate"},
    ]}, dataset_ids=IDS)
    assert len(g["edges"]) == len(g["nodes"]) - 1
    assert len({e["id"] for e in g["edges"]}) == len(g["edges"])


def test_node_ids_are_unique_when_a_type_repeats():
    g = steps_to_graph({"buoc": [
        {"loai": "retrieve", "dataset_ids": [DS1]},
        {"loai": "retrieve", "dataset_ids": [DS2]},
    ]}, dataset_ids=IDS)
    ids = [n["id"] for n in g["nodes"]]
    assert len(ids) == len(set(ids))
    assert "retrieve" in ids and "retrieve_2" in ids


def test_nodes_never_overlap():
    g = steps_to_graph({"buoc": [
        {"loai": "if_else", "variable": "x", "operator": "exists",
         "neu_dung": [{"loai": "retrieve", "dataset_ids": [DS1]}, {"loai": "answer"}],
         "neu_sai": [{"loai": "retrieve", "dataset_ids": [DS2]}, {"loai": "answer"}]},
    ]}, dataset_ids=IDS)
    pos = positions(g)
    assert len(pos) == len(set(pos))


# --------------------------------------------------------------------------- rẽ nhánh

def test_branch_emits_true_edge_first():
    """Runtime đọc THỨ TỰ cạnh, không đọc sourceHandle. Đảo thứ tự là luồng chạy ngược."""
    g = steps_to_graph({"buoc": [
        {"loai": "if_else", "variable": "extracted_params.y", "operator": "equals", "value": "a",
         "neu_dung": [{"loai": "retrieve", "dataset_ids": [DS1], "nhan": "nhánh đúng"}],
         "neu_sai": [{"loai": "retrieve", "dataset_ids": [DS2], "nhan": "nhánh sai"}]},
    ]}, dataset_ids=IDS)
    out = [e for e in g["edges"] if e["source"] == "if_else"]
    assert len(out) == 2
    labels = [next(n["data"]["label"] for n in g["nodes"] if n["id"] == e["target"]) for e in out]
    assert labels == ["nhánh đúng", "nhánh sai"]
    assert [e.get("sourceHandle") for e in out] == ["true", "false"]


def test_branches_rejoin_on_the_next_step():
    g = steps_to_graph({"buoc": [
        {"loai": "if_else", "variable": "x", "operator": "exists",
         "neu_dung": [{"loai": "retrieve", "dataset_ids": [DS1]}],
         "neu_sai": [{"loai": "retrieve", "dataset_ids": [DS2]}]},
        {"loai": "llm_generate"},
    ]}, dataset_ids=IDS)
    into_llm = {e["source"] for e in g["edges"] if e["target"] == "llm_generate"}
    assert into_llm == {"retrieve", "retrieve_2"}


def test_empty_branch_is_refused():
    with pytest.raises(ValidationError, match="ít nhất một bước"):
        steps_to_graph({"buoc": [
            {"loai": "if_else", "variable": "x", "operator": "exists",
             "neu_dung": [], "neu_sai": [{"loai": "answer"}]}]})


def test_input_inside_a_branch_is_refused():
    with pytest.raises(ValidationError, match="bên trong một nhánh"):
        steps_to_graph({"buoc": [
            {"loai": "if_else", "variable": "x", "operator": "exists",
             "neu_dung": [{"loai": "input"}], "neu_sai": [{"loai": "answer"}]}]})


# --------------------------------------------------------------------------- thông báo lỗi

def test_error_points_at_the_step_the_model_wrote():
    """Nói 'Node if_else_2' thì mô hình không biết sửa đâu, id đó do máy chủ đặt."""
    with pytest.raises(ValidationError, match=r"^bước 2"):
        steps_to_graph({"buoc": [
            {"loai": "answer"},
            {"loai": "retrieve"},
        ]})


def test_step_numbering_survives_a_branch():
    """Biến vòng lặp của nhánh từng đè lên bộ bù số thứ tự, làm các bước sau nhánh báo sai số."""
    with pytest.raises(ValidationError, match=r"^bước 3"):
        steps_to_graph({"buoc": [
            {"loai": "if_else", "variable": "x", "operator": "exists",
             "neu_dung": [{"loai": "answer"}], "neu_sai": [{"loai": "answer"}]},
            {"loai": "llm_generate"},
            {"loai": "retrieve"},
        ]})


def test_error_names_the_branch():
    with pytest.raises(ValidationError, match="nhánh sai"):
        steps_to_graph({"buoc": [
            {"loai": "if_else", "variable": "x", "operator": "exists",
             "neu_dung": [{"loai": "retrieve", "dataset_ids": [DS1]}],
             "neu_sai": [{"loai": "retrieve"}]}]}, dataset_ids=IDS)


def test_unknown_step_type_lists_the_allowed_ones():
    with pytest.raises(ValidationError, match="retrieve"):
        steps_to_graph({"buoc": [{"loai": "magic"}]})


def test_missing_steps_key():
    with pytest.raises(ValidationError, match="buoc"):
        steps_to_graph({"ten": "không có bước"})


def test_too_many_steps():
    with pytest.raises(ValidationError, match=str(MAX_STEPS)):
        steps_to_graph({"buoc": [{"loai": "answer"} for _ in range(MAX_STEPS + 1)]})


# --------------------------------------------------------------------------- làm sạch dữ liệu

def test_unknown_fields_are_dropped():
    """Mô hình bịa thêm trường thì bỏ, đừng để nó đọng lại trong graph_json."""
    g = steps_to_graph({"buoc": [
        {"loai": "retrieve", "dataset_ids": [DS1], "mau_sac": "xanh", "top_k": 3}]}, dataset_ids=IDS)
    data = next(n["data"] for n in g["nodes"] if n["type"] == "retrieve")
    assert "mau_sac" not in data
    assert data["top_k"] == 3


def test_label_falls_back_to_the_node_name():
    g = steps_to_graph({"buoc": [{"loai": "llm_generate"}]})
    assert next(n["data"]["label"] for n in g["nodes"] if n["type"] == "llm_generate")


# --------------------------------------------------------------------------- dịch ngược

def test_round_trip_of_the_seeded_router():
    from app.seed_demo import _router_graph

    ds1, ds2 = uuid.uuid4(), uuid.uuid4()
    steps = graph_to_steps(_router_graph(ds1, ds2))
    assert not steps.get("khong_day_du")
    assert [s["loai"] for s in steps["buoc"]] == [
        "parameter_extract", "if_else", "compose_prompt", "llm_generate", "answer"]
    branch = steps["buoc"][1]
    assert [s["loai"] for s in branch["neu_dung"]] == ["retrieve"]
    assert [s["loai"] for s in branch["neu_sai"]] == ["retrieve"]

    rebuilt = steps_to_graph(steps, dataset_ids={str(ds1), str(ds2)})
    assert types_of(rebuilt) == types_of(_router_graph(ds1, ds2))


def test_graph_without_input_is_reported_incomplete():
    assert graph_to_steps({"nodes": [], "edges": []})["khong_day_du"] is True
