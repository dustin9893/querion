"""Token usage metering.

Every model call records one ``token_usage`` row: which component spent the tokens (answer,
agent round, workflow step, title, query / document embedding), on which channel, for which
assistant and unit, with which provider and model. Providers report exact counts; when one
does not (some gateways omit usage on streams), the row is an estimate (~3 characters per token
for Vietnamese text) flagged ``estimated``.

Rows are written in their own short session so metering never touches the request's
transaction, and a failure to record is logged, never raised into the answer.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from typing import Any

logger = logging.getLogger(__name__)

COMPONENTS = ("answer", "agent", "workflow_llm", "workflow_extract", "form_suggest", "title",
              "query_embedding", "document_embedding")
CHARS_PER_TOKEN = 3


@dataclass(frozen=True)
class UsageScope:
    """Who the tokens are billed to. Built from the audit run when there is one."""

    workspace_id: uuid.UUID | None = None
    app_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    channel: str | None = None
    dataset_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None

    @classmethod
    def of_run(cls, run: Any, **extra: Any) -> "UsageScope":
        if run is None:
            return cls(**extra)
        return cls(workspace_id=run.workspace_id, app_id=run.app_id, run_id=run.id, channel=run.channel, **extra)

    def but(self, **changes: Any) -> "UsageScope":
        return replace(self, **changes)


@dataclass
class TokenMeter:
    """Filled by a vendor call with the counts the provider reported (None = not reported)."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def set(self, prompt: int | None, completion: int | None) -> None:
        """Latest report wins (streams may repeat a running total)."""
        if prompt is not None:
            self.prompt_tokens = int(prompt)
        if completion is not None:
            self.completion_tokens = int(completion)

    def add(self, prompt: int | None, completion: int | None) -> None:
        if prompt is not None:
            self.prompt_tokens = (self.prompt_tokens or 0) + int(prompt)
        if completion is not None:
            self.completion_tokens = (self.completion_tokens or 0) + int(completion)

    @property
    def reported(self) -> bool:
        return self.prompt_tokens is not None or self.completion_tokens is not None


def estimate_tokens(text: str | None) -> int:
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN if text else 0


def messages_text(messages: list[dict] | list[Any]) -> str:
    parts = []
    for m in messages:
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        parts.append(content if isinstance(content, str) else str(content or ""))
    return "\n".join(parts)


async def record_usage(
    scope: UsageScope | None,
    *,
    component: str,
    purpose: str,
    provider: Any = None,
    meter: TokenMeter | None = None,
    prompt_text: str | None = None,
    completion_text: str | None = None,
    calls: int = 1,
    model: str | None = None,
) -> None:
    """Write one usage row. Uses the meter when the provider reported counts, else estimates."""
    try:
        from app.db import async_session_factory
        from app.models.usage import TokenUsage

        scope = scope or UsageScope()
        estimated = not (meter and meter.reported)
        if estimated:
            prompt, completion = estimate_tokens(prompt_text), estimate_tokens(completion_text)
        else:
            prompt, completion = meter.prompt_tokens or 0, meter.completion_tokens or 0
        if prompt == 0 and completion == 0:
            return
        row = TokenUsage(
            workspace_id=scope.workspace_id, app_id=scope.app_id, run_id=scope.run_id,
            dataset_id=scope.dataset_id, document_id=scope.document_id, channel=scope.channel,
            component=component, purpose=purpose,
            provider=getattr(provider, "provider_name", None),
            model=model or getattr(provider, "model_name", None),
            prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion,
            calls=calls, estimated=estimated,
        )
        async with async_session_factory() as session:
            session.add(row)
            await session.commit()
    except Exception:
        logger.warning("could not record token usage (%s)", component, exc_info=True)
