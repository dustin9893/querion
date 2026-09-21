"""Kiểm cấu hình bong bóng Trợ lý Vận hành.

Phần lớn bài ở đây bảo vệ một thứ: **gợi ý tự bật không được trở thành phiền toái**. Trần cứng,
id không trùng, nội dung không dài lê thê.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.services.ops import (
    DEFAULT_TIPS,
    PREVIOUS_SYSTEM_PROMPTS,
    MAX_TIP_TEXT,
    MAX_TIPS,
    OPS_SYSTEM_PROMPT,
    OpsActor,
    audit_scope,
    scope_workspaces,
    tips_for,
    validate_roles,
    validate_tips,
)


def actor(**kw) -> OpsActor:
    base = dict(user_id=uuid.uuid4(), role="admin", is_super=False, member=[], owned=[])
    base.update(kw)
    return OpsActor(**base)


# --------------------------------------------------------------------------- gợi ý

def test_default_tips_are_valid():
    """Gợi ý mặc định đi vào cơ sở dữ liệu lúc seed, nên phải qua đúng bộ kiểm của API."""
    assert validate_tips(DEFAULT_TIPS) == validate_tips(DEFAULT_TIPS)
    assert len(validate_tips(DEFAULT_TIPS)) == len(DEFAULT_TIPS)


def test_duplicate_tip_id_is_refused():
    """Trình duyệt nhớ 'đã xem' theo id; trùng id thì một gợi ý không bao giờ hiện."""
    with pytest.raises(HTTPException, match="trùng id"):
        validate_tips([{"id": "a", "text": "x"}, {"id": "a", "text": "y"}])


def test_tip_needs_id_and_text():
    with pytest.raises(HTTPException, match="thiếu 'id'"):
        validate_tips([{"text": "x"}])
    with pytest.raises(HTTPException, match="thiếu nội dung"):
        validate_tips([{"id": "a", "text": "   "}])


def test_tip_text_length_is_capped():
    with pytest.raises(HTTPException, match=str(MAX_TIP_TEXT)):
        validate_tips([{"id": "a", "text": "x" * (MAX_TIP_TEXT + 1)}])


def test_route_must_be_a_path():
    with pytest.raises(HTTPException, match="dấu /"):
        validate_tips([{"id": "a", "text": "x", "route": "datasets"}])
    assert validate_tips([{"id": "a", "text": "x", "route": "/datasets"}])[0]["route"] == "/datasets"


def test_too_many_tips():
    with pytest.raises(HTTPException, match=str(MAX_TIPS)):
        validate_tips([{"id": f"t{i}", "text": "x"} for i in range(MAX_TIPS + 1)])


def test_unknown_keys_are_dropped():
    out = validate_tips([{"id": "a", "text": "x", "mau": "đỏ"}])
    assert out == [{"id": "a", "text": "x"}]


def test_empty_tips_allowed():
    assert validate_tips([]) == []
    assert validate_tips(None) == []


def test_tips_are_filtered_by_role():
    class Cfg:
        tips = [
            {"id": "a", "text": "cho mọi người"},
            {"id": "b", "text": "chỉ super", "roles": ["super_admin"]},
        ]
    assert [t["id"] for t in tips_for(Cfg(), "admin")] == ["a"]
    assert {t["id"] for t in tips_for(Cfg(), "super_admin")} == {"a", "b"}


# --------------------------------------------------------------------------- vai trò

def test_roles_must_be_known():
    with pytest.raises(HTTPException, match="không hợp lệ"):
        validate_roles(["admin", "staff"])


def test_roles_cannot_be_empty():
    with pytest.raises(HTTPException, match="ít nhất một vai trò"):
        validate_roles([])


def test_roles_come_back_in_a_stable_order():
    assert validate_roles(["super_admin", "admin"]) == ["admin", "super_admin"]


# --------------------------------------------------------------------------- hai phạm vi

def test_config_scope_uses_membership_not_ownership():
    """Kho tri thức và công cụ là thứ quản trị viên đã thấy trên giao diện với vai trò editor.
    Bắt phải là owner mới liệt kê được thì trợ lý còn kém hơn chính sản phẩm."""
    ws = uuid.uuid4()
    a = actor(member=[ws], owned=[], active_workspace_id=ws)
    assert scope_workspaces(a) == [ws]
    assert a.may_configure(ws) is True
    assert a.may_audit(ws) is False


def test_audit_scope_stays_owner_only():
    """Dữ liệu kiểu nhật ký đi theo đúng luật trang nhật ký truy vấn."""
    owned, seen_only = uuid.uuid4(), uuid.uuid4()
    a = actor(member=[owned, seen_only], owned=[owned], active_workspace_id=seen_only)
    # đơn vị đang mở không phải của mình -> lùi về danh sách sở hữu, không mở rộng
    assert audit_scope(a) == [owned]
    assert a.may_audit(seen_only) is False


def test_super_admin_is_unrestricted():
    a = actor(is_super=True, role="super_admin", member=None, owned=None)
    assert scope_workspaces(a) is None
    assert audit_scope(a) is None
    assert a.may_configure(uuid.uuid4()) is True
    assert a.may_audit(uuid.uuid4()) is True


def test_admin_with_no_units_sees_nothing():
    a = actor(member=[], owned=[])
    assert scope_workspaces(a) == []
    assert audit_scope(a) == []
    assert a.may_configure(uuid.uuid4()) is False


# --------------------------------------------------------------------------- prompt

def test_system_prompt_forbids_inventing_ui_paths():
    assert "không bịa" in OPS_SYSTEM_PROMPT.lower() or "Tuyệt đối không bịa" in OPS_SYSTEM_PROMPT


def test_system_prompt_says_it_never_changes_anything():
    assert "không tự thay đổi cấu hình" in OPS_SYSTEM_PROMPT


def test_system_prompt_has_a_context_slot():
    assert "{context}" in OPS_SYSTEM_PROMPT


def test_system_prompt_forbids_citation_markers():
    """Trợ lý này hướng dẫn dùng phần mềm, không tra quy định ngân hàng. Dán [#3] vào giữa câu chỉ
    làm câu văn gãy và không ai bấm vào."""
    assert "không chèn ký hiệu trích dẫn" in OPS_SYSTEM_PROMPT
    assert "Trích dẫn bằng [#n]" not in OPS_SYSTEM_PROMPT


def test_previous_prompts_are_kept_for_safe_upgrades():
    """`seed_ops` so prompt đang lưu với danh sách này để biết super admin đã sửa hay chưa.
    Danh sách rỗng nghĩa là mọi bản deploy sau sẽ không bao giờ nâng được prompt mặc định."""
    assert PREVIOUS_SYSTEM_PROMPTS
    assert OPS_SYSTEM_PROMPT not in PREVIOUS_SYSTEM_PROMPTS
    assert all("{context}" in old for old in PREVIOUS_SYSTEM_PROMPTS)
