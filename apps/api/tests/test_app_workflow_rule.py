"""A report workflow may not become an assistant's brain — but a binding made before that rule
existed must not lock the assistant.

The web page saves the whole assistant at once, so if the check rejected an unchanged binding the
owner could not even tick a tool or clear the workflow: every save came back 400.

Run: cd apps/api && pytest tests/test_app_workflow_rule.py -v
"""

import uuid

import pytest
from fastapi import HTTPException

from app.routers.apps import _check_chat_workflow


class _Workflow:
    def __init__(self, workspace_id, wf_type):
        self.workspace_id = workspace_id
        self.type = wf_type


class _Db:
    """Stands in for the session: _check_chat_workflow only ever calls get()."""

    def __init__(self, workflow):
        self._workflow = workflow

    async def get(self, _model, _id):
        return self._workflow


WS = uuid.uuid4()
REPORT_ID = str(uuid.uuid4())
CHAT_ID = str(uuid.uuid4())


@pytest.mark.asyncio
async def test_binding_a_report_workflow_is_refused():
    db = _Db(_Workflow(WS, "report"))
    with pytest.raises(HTTPException) as err:
        await _check_chat_workflow(db, REPORT_ID, WS)
    assert err.value.status_code == 400
    assert "công cụ" in err.value.detail.lower()


@pytest.mark.asyncio
async def test_switching_to_another_report_workflow_is_refused():
    db = _Db(_Workflow(WS, "report"))
    with pytest.raises(HTTPException):
        await _check_chat_workflow(db, REPORT_ID, WS, current=uuid.UUID(CHAT_ID))


@pytest.mark.asyncio
async def test_an_existing_report_binding_stays_editable():
    """The assistant keeps the old value, so the rest of the save must go through."""
    db = _Db(_Workflow(WS, "report"))
    await _check_chat_workflow(db, REPORT_ID, WS, current=uuid.UUID(REPORT_ID))


@pytest.mark.asyncio
async def test_clearing_the_workflow_is_always_allowed():
    db = _Db(_Workflow(WS, "report"))
    await _check_chat_workflow(db, "", WS, current=uuid.UUID(REPORT_ID))
    await _check_chat_workflow(db, None, WS, current=uuid.UUID(REPORT_ID))


@pytest.mark.asyncio
async def test_a_chat_workflow_of_the_unit_is_allowed():
    db = _Db(_Workflow(WS, "chatflow"))
    await _check_chat_workflow(db, CHAT_ID, WS)


@pytest.mark.asyncio
async def test_a_workflow_of_another_unit_is_not_found():
    db = _Db(_Workflow(uuid.uuid4(), "chatflow"))
    with pytest.raises(HTTPException) as err:
        await _check_chat_workflow(db, CHAT_ID, WS)
    assert err.value.status_code == 404


@pytest.mark.asyncio
async def test_a_malformed_id_is_a_clear_400():
    db = _Db(None)
    with pytest.raises(HTTPException) as err:
        await _check_chat_workflow(db, "khong-phai-uuid", WS)
    assert err.value.status_code == 400
