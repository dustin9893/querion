"""Workflow/Chatflow runtime — execute graph_json via node chain.

Supports linear chain + if_else branching.
Each node transforms the state dict sequentially.
"""

import ipaddress
import json
import logging
import re
import socket
from urllib.parse import urlparse

import httpx
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.retrieval import retrieve
from app.services.encryption import decrypt_key
from app.services.observability import log_step_start, log_step_end, complete_run
from app.models.run import Run
from app.services.tools.executor import ToolError, as_untrusted_block
from app.services.usage import TokenMeter, UsageScope, messages_text, record_usage

logger = logging.getLogger(__name__)


async def run_workflow(
    db: AsyncSession,
    graph_json: dict[str, Any],
    query: str,
    inputs: dict[str, Any] | None = None,
    history: list[dict] | None = None,
    run: Run | None = None,
    workspace_id: Any = None,
    schedule_id: Any = None,
    actor_employee_id: Any = None,
    actor_user_id: Any = None,
) -> dict[str, Any]:
    """Execute a validated workflow/chatflow graph and return answer + citations.

    Args:
        history: conversation history for chatflow memory (list of {role, content})
        workspace_id: unit the run belongs to — required by ``tool_call`` (which tools may be
            used) and ``render_document`` (where the file is stored and who may read it).
    """
    nodes = graph_json.get("nodes", [])
    edges = graph_json.get("edges", [])

    node_map = {n["id"]: n for n in nodes}

    # Build adjacency list (support multiple outgoing for if_else)
    adj: dict[str, list[dict]] = {n["id"]: [] for n in nodes}
    for edge in edges:
        adj[edge["source"]].append(edge)

    # Find start node
    in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}
    for edge in edges:
        in_degree[edge["target"]] = in_degree.get(edge["target"], 0) + 1

    start = None
    for n in nodes:
        if n["type"] == "input" and in_degree[n["id"]] == 0:
            start = n["id"]
            break

    if not start:
        raise RuntimeError("No input node found")

    # Initialize state
    state: dict[str, Any] = {
        "query": query,
        "inputs": inputs or {},
        "retrieved_chunks": [],
        "prompt_messages": [],
        "answer": "",
        "citations": [],
        "extracted_params": {},
        "history": history or [],
        "tool_results": {},
        "artifacts": [],
        "workspace_id": workspace_id,
        "run_id": getattr(run, "id", None),
        "workflow_id": getattr(run, "workflow_id", None),
        "schedule_id": schedule_id,
        "actor_employee_id": actor_employee_id,
        "actor_user_id": actor_user_id,
    }

    # An input node may declare the fields a report / form run expects; check them once up front
    # so a scheduled run fails with a readable message instead of an empty report.
    input_fields = (node_map[start].get("data") or {}).get("fields") or []
    if input_fields:
        state["inputs"] = _coerce_inputs(input_fields, state["inputs"])

    # Execute graph (supports if_else branching)
    current_id: str | None = start
    visited = set()

    while current_id:
        if current_id in visited:
            break  # prevent infinite loops
        visited.add(current_id)

        node = node_map[current_id]
        node_type = node["type"]
        node_data = node.get("data", {})

        # Log step start (if observability enabled)
        step = None
        if run:
            step = await log_step_start(db, run_id=run.id, node_id=current_id, node_type=node_type,
                                        input_data={"query": state["query"][:200]})

        await _execute_node(db, node_type, node_data, state, usage=UsageScope.of_run(run))

        # Log step end
        if run and step:
            output_preview = {"answer": state.get("answer", "")[:200]}
            if state.get("extracted_params"):
                output_preview["extracted_params"] = state["extracted_params"]
            await log_step_end(step, output_data=output_preview)

        # Find next node
        outgoing = adj.get(current_id, [])
        if not outgoing:
            break
        elif node_type == "if_else" and len(outgoing) >= 2:
            # If/else: pick branch based on condition result
            branch = state.get("_branch", "true")
            # Convention: first edge = true, second edge = false
            # Or use sourceHandle: "true"/"false"
            true_edge = None
            false_edge = None
            for edge in outgoing:
                handle = edge.get("sourceHandle", "")
                if handle == "false" or edge == outgoing[-1]:
                    false_edge = edge
                else:
                    true_edge = edge
            if len(outgoing) == 2:
                true_edge = outgoing[0]
                false_edge = outgoing[1]

            current_id = true_edge["target"] if branch == "true" else false_edge["target"]
        else:
            current_id = outgoing[0]["target"]

    # Complete run
    if run:
        await complete_run(run, status="completed")

    return {
        "answer": state["answer"],
        "extracted_params": state.get("extracted_params", {}),
        "artifacts": state.get("artifacts", []),
        "tool_results": state.get("tool_results", {}),
        "retriever_resources": [
            {
                "chunk_id": c.get("chunk_id"),
                "content_preview": c.get("content_preview", ""),
                "chunk_index": c.get("chunk_index"),
                "document_id": c.get("document_id"),
                "dataset_id": c.get("dataset_id"),
                "filename": c.get("filename", ""),
                "content": c.get("content", ""),
                "doc_type": c.get("doc_type"),
                "version": c.get("version"),
                "effective_from": c.get("effective_from"),
                "section": c.get("section"),
                "score": c.get("score", 0),
            }
            for c in state["citations"]
        ],
    }


async def _execute_node(
    db: AsyncSession,
    node_type: str,
    node_data: dict[str, Any],
    state: dict[str, Any],
    usage: UsageScope | None = None,
) -> None:
    """Execute a single node and update state. ``usage`` bills model calls to the run."""

    if node_type == "input":
        pass

    elif node_type == "retrieve":
        dataset_ids_raw = node_data.get("dataset_ids", [])
        top_k = node_data.get("top_k", 5)
        if dataset_ids_raw:
            dataset_ids = [UUID(d) if isinstance(d, str) else d for d in dataset_ids_raw]
            chunks = await retrieve(db=db, query=state["query"], dataset_ids=dataset_ids, top_k=top_k, usage=usage)
            state["retrieved_chunks"] = chunks
            state["citations"] = chunks

    elif node_type == "compose_prompt":
        template = node_data.get("template", "{{query}}")
        context_parts = []
        for i, chunk in enumerate(state["retrieved_chunks"]):
            context_parts.append(f"[#{i}] {chunk['content']}")
        context = "\n\n".join(context_parts) if context_parts else ""

        prompt_text = template.replace("{{query}}", state["query"])
        prompt_text = prompt_text.replace("{{context}}", context)
        prompt_text = prompt_text.replace("{{system_prompt}}", node_data.get("system_prompt", ""))
        if "{{tool_results}}" in prompt_text:
            # Tool output is data from another system: wrap it like retrieved documents so the
            # model treats instructions inside it as text, never as commands.
            blocks = "\n\n".join(
                as_untrusted_block(alias, json.dumps(value, ensure_ascii=False, default=str))
                for alias, value in (state.get("tool_results") or {}).items()
            )
            prompt_text = prompt_text.replace("{{tool_results}}", blocks)
        prompt_text = prompt_text.replace("{{answer}}", state.get("answer", ""))
        for key, value in (state.get("inputs") or {}).items():
            prompt_text = prompt_text.replace(f"{{{{inputs.{key}}}}}", "" if value is None else str(value))

        # Include history for chatflow memory
        messages: list[dict] = []
        if prompt_text:
            messages.append({"role": "system", "content": prompt_text})
        for h in state.get("history", []):
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": state["query"]})
        state["prompt_messages"] = messages

    elif node_type == "llm_generate":
        from app.services.chat import get_active_llm_provider
        provider = await get_active_llm_provider(db)
        if not provider:
            state["answer"] = "Error: No active LLM provider configured."
            return

        api_key = decrypt_key(provider.api_key_encrypted)
        model = node_data.get("model") or provider.model_name
        temperature = node_data.get("temperature", 0.7)
        max_tokens = node_data.get("max_tokens", 4096)
        messages = state["prompt_messages"] or [{"role": "user", "content": state["query"]}]

        meter = TokenMeter()
        answer = await _call_llm(
            provider_name=provider.provider_name,
            api_key=api_key, model=model,
            messages=messages,
            temperature=temperature, max_tokens=max_tokens,
            base_url=provider.base_url, meter=meter,
        )
        state["answer"] = answer
        await record_usage(usage, component="workflow_llm", purpose="llm", provider=provider, meter=meter,
                           prompt_text=messages_text(messages), completion_text=answer)

    elif node_type == "parameter_extract":
        # Use LLM to extract structured parameters from the latest message
        schema = node_data.get("schema", {})
        # schema: {"field_name": "field_description", ...}
        if not schema:
            return

        schema_desc = "\n".join(f"- {k}: {v}" for k, v in schema.items())
        extraction_prompt = f"""Extract the following fields from the conversation. Return ONLY valid JSON, nothing else.

Fields to extract:
{schema_desc}

If a field cannot be determined from the conversation, use null.
"""
        # Build context: history + current query
        conversation_text = ""
        for h in state.get("history", []):
            conversation_text += f"{h['role']}: {h['content']}\n"
        conversation_text += f"user: {state['query']}\n"

        extract_messages = [
            {"role": "system", "content": extraction_prompt},
            {"role": "user", "content": conversation_text},
        ]

        from app.services.chat import get_active_llm_provider
        provider = await get_active_llm_provider(db)
        if provider:
            api_key = decrypt_key(provider.api_key_encrypted)
            meter = TokenMeter()
            raw = await _call_llm(
                provider_name=provider.provider_name,
                api_key=api_key, model=provider.model_name,
                messages=extract_messages,
                temperature=0.0, max_tokens=1024,
                base_url=provider.base_url, meter=meter,
            )
            await record_usage(usage, component="workflow_extract", purpose="llm", provider=provider, meter=meter,
                               prompt_text=messages_text(extract_messages), completion_text=raw)
            # Parse JSON from response
            try:
                # Strip markdown code fences if present
                clean = re.sub(r"```json?\s*", "", raw)
                clean = re.sub(r"```\s*$", "", clean).strip()
                extracted = json.loads(clean)
                state["extracted_params"] = extracted
            except json.JSONDecodeError:
                state["extracted_params"] = {"_raw": raw}

    elif node_type == "http_request":
        # Call external API
        url = node_data.get("url", "")
        method = node_data.get("method", "POST").upper()
        headers = node_data.get("headers", {})
        body_template = node_data.get("body_template", "")

        if not url:
            return
        blocked = _http_target_blocked(url)
        if blocked:
            state["http_response"] = {"status": 0, "body": f"Blocked: {blocked}"}
            return

        # Replace variables in body template
        body_str = body_template
        body_str = body_str.replace("{{query}}", state["query"])
        body_str = body_str.replace("{{answer}}", state.get("answer", ""))
        # Replace extracted params
        for k, v in state.get("extracted_params", {}).items():
            body_str = body_str.replace(f"{{{{{k}}}}}", str(v) if v is not None else "")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                elif method == "PUT":
                    resp = await client.put(url, headers=headers, content=body_str)
                elif method == "DELETE":
                    resp = await client.delete(url, headers=headers)
                else:  # POST
                    resp = await client.post(url, headers=headers, content=body_str)

                state["http_response"] = {
                    "status": resp.status_code,
                    "body": resp.text[:2000],
                }
        except Exception as e:
            state["http_response"] = {"status": 0, "body": str(e)}

    elif node_type == "tool_call":
        # Call a tool from the unit's registry (same policy as the agent: SSRF guard, secret
        # injected server-side, args checked against the tool's JSON Schema).
        alias = str(node_data.get("alias") or "ket_qua")
        try:
            state["tool_results"][alias] = await _run_registry_tool(
                db, state.get("workspace_id"), node_data, state,
            )
        except ToolError as exc:
            state["tool_results"][alias] = {"loi": str(exc)}
        except Exception as exc:  # never kill a whole report because one system is down
            logger.exception("tool_call node failed")
            state["tool_results"][alias] = {"loi": f"{type(exc).__name__}: {exc}"}

    elif node_type == "render_document":
        await _render_document_node(db, node_data, state)

    elif node_type == "if_else":
        # Evaluate condition and set branch
        variable = node_data.get("variable", "")  # e.g. "extracted_params.name"
        operator = node_data.get("operator", "exists")  # exists, equals, contains, not_empty
        compare_value = node_data.get("value", "")

        # Resolve variable from state
        actual_value = _resolve_variable(state, variable)

        if operator == "exists":
            result = actual_value is not None
        elif operator == "not_empty":
            result = bool(actual_value)
        elif operator == "equals":
            result = str(actual_value) == str(compare_value)
        elif operator == "contains":
            result = str(compare_value) in str(actual_value or "")
        else:
            result = bool(actual_value)

        state["_branch"] = "true" if result else "false"

    elif node_type == "answer":
        # Answer node for chatflow — uses answer from state or generates one
        template = node_data.get("template", "")
        if template:
            answer = template
            answer = answer.replace("{{answer}}", state.get("answer", ""))
            answer = answer.replace("{{query}}", state["query"])
            for k, v in state.get("extracted_params", {}).items():
                answer = answer.replace(f"{{{{{k}}}}}", str(v) if v is not None else "")
            http_resp = state.get("http_response", {})
            answer = answer.replace("{{http_status}}", str(http_resp.get("status", "")))
            state["answer"] = answer
        # If no template, keep existing answer from llm_generate

    elif node_type == "code_execute":
        # Execute Python code in a restricted sandbox
        code = node_data.get("code", "")
        if not code.strip():
            return
        if not settings.ENABLE_CODE_EXECUTE:
            state["code_output"] = {"error": "code_execute is disabled (set ENABLE_CODE_EXECUTE=true to allow; it is not a sandbox)"}
            return

        # Prepare arguments accessible to the code
        args = {
            "query": state["query"],
            "inputs": state.get("inputs", {}),
            "answer": state.get("answer", ""),
            "extracted_params": state.get("extracted_params", {}),
            "retrieved_chunks": state.get("retrieved_chunks", []),
            "http_response": state.get("http_response", {}),
        }

        # Safe builtins
        safe_builtins = {
            "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
            "enumerate": enumerate, "filter": filter, "float": float,
            "int": int, "isinstance": isinstance, "len": len, "list": list,
            "map": map, "max": max, "min": min, "print": print, "range": range,
            "round": round, "set": set, "sorted": sorted, "str": str,
            "sum": sum, "tuple": tuple, "type": type, "zip": zip,
            "True": True, "False": False, "None": None,
            "json": json, "re": re,
        }

        sandbox: dict[str, Any] = {"__builtins__": safe_builtins, "args": args}

        try:
            exec(code, sandbox)
            # Call main(args) if defined
            if "main" in sandbox and callable(sandbox["main"]):
                result = sandbox["main"](args)
                if isinstance(result, dict):
                    # Merge results back into state
                    if "answer" in result:
                        state["answer"] = result["answer"]
                    if "extracted_params" in result:
                        state["extracted_params"].update(result["extracted_params"])
                    # Store full return
                    state["code_output"] = result
                else:
                    state["code_output"] = result
            elif "result" in sandbox:
                state["code_output"] = sandbox["result"]
        except Exception as e:
            state["code_output"] = {"error": str(e)}

    elif node_type == "output":
        pass


def _http_target_blocked(url: str) -> str | None:
    """Return a reason if the http_request target must not be called (SSRF guard)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "invalid URL"
    if parsed.scheme not in ("http", "https"):
        return "only http/https allowed"
    host = parsed.hostname or ""
    if not host:
        return "missing host"
    if settings.HTTP_REQUEST_ALLOW_PRIVATE:
        return None
    if host.lower() in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
        return "internal hostname not allowed"
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return "host does not resolve"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return f"target resolves to a non-public address ({ip})"
    return None


def _resolve_variable(state: dict, path: str) -> Any:
    """Resolve a dot-path variable from state. E.g. 'extracted_params.name'"""
    parts = path.split(".")
    current: Any = state
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


# ---------------------------------------------------------------------------
# Report nodes: input schema, registry tools, document rendering
# ---------------------------------------------------------------------------

INPUT_FIELD_TYPES = ("string", "text", "number", "date", "select", "boolean")


def _coerce_inputs(fields: list[dict], inputs: dict[str, Any]) -> dict[str, Any]:
    """Check run inputs against the input node's declared fields and convert the types.

    The same field list drives the "Chạy" dialog, the schedule editor and the staff form, so a
    readable error here is what a scheduled run reports when someone changes the workflow.
    """
    out: dict[str, Any] = dict(inputs or {})
    for field in fields:
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        ftype = field.get("type") or "string"
        value = out.get(name, field.get("default"))
        if value in (None, ""):
            if field.get("required"):
                raise RuntimeError(f"Thiếu tham số bắt buộc: {field.get('label') or name}")
            out[name] = field.get("default") if field.get("default") is not None else ""
            continue
        if ftype == "number":
            try:
                out[name] = float(str(value).replace(",", "."))
            except (TypeError, ValueError):
                raise RuntimeError(f"Tham số '{field.get('label') or name}' phải là số")
        elif ftype == "boolean":
            out[name] = value if isinstance(value, bool) else str(value).lower() in ("true", "1", "yes", "có")
        elif ftype == "select":
            options = [str(o) for o in (field.get("options") or [])]
            if options and str(value) not in options:
                raise RuntimeError(f"Tham số '{field.get('label') or name}' phải là một trong: {', '.join(options)}")
            out[name] = str(value)
        else:
            out[name] = str(value)
    return out


def _render_args(value: Any, state: dict[str, Any]) -> Any:
    """Substitute {{inputs.x}} / {{params.x}} / {{query}} inside tool arguments."""
    if isinstance(value, dict):
        return {k: _render_args(v, state) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_args(v, state) for v in value]
    if not isinstance(value, str):
        return value
    exact = re.fullmatch(r"\{\{\s*([\w.]+)\s*\}\}", value)
    if exact:  # a lone placeholder keeps the real type (number stays a number)
        resolved = _resolve_variable(state, exact.group(1))
        return resolved if resolved is not None else ""

    def repl(match: "re.Match[str]") -> str:
        resolved = _resolve_variable(state, match.group(1))
        return "" if resolved is None else str(resolved)

    return re.sub(r"\{\{\s*([\w.]+)\s*\}\}", repl, value)


async def _run_registry_tool(db: AsyncSession, workspace_id: Any, node_data: dict, state: dict[str, Any]) -> Any:
    """Run the node's registry tool with its arguments rendered from the run state."""
    from app.services.tools.registry import run_tool_by_id

    args = _render_args(node_data.get("args") or {}, state)
    if not isinstance(args, dict):
        raise ToolError("args của công cụ phải là object")
    return await run_tool_by_id(db, workspace_id, node_data.get("tool_id"), args,
                                mcp_tool=node_data.get("mcp_tool"))


async def _render_document_node(db: AsyncSession, node_data: dict, state: dict[str, Any]) -> None:
    """Render the report/form file and record it as an artifact."""
    from app.services.reports import (
        DOCX_MIME, MARKDOWN_MIME, XLSX_MIME, ReportError, build_context, render_docx, render_markdown,
        render_xlsx, safe_filename, store_artifact,
    )
    from app.storage import download_file

    workspace_id = state.get("workspace_id")
    if workspace_id is None:
        state["artifacts"].append({"error": "Luồng xử lý chưa gắn đơn vị nên không xuất được file"})
        return

    # `vars` lets a template read short names ({{ danh_sach }}) instead of deep paths, and the
    # values keep their real type because a lone {{...}} placeholder resolves to the object.
    extra = _render_args(node_data.get("vars") or {}, state)
    context = build_context(state, extra=extra if isinstance(extra, dict) else {})
    fmt = str(node_data.get("format") or "markdown").lower()
    try:
        title = render_markdown(str(node_data.get("title") or "Báo cáo"), context)
        name = render_markdown(str(node_data.get("filename") or title), context)
        if fmt == "docx":
            key = node_data.get("template_key")
            if not key:
                raise ReportError("Node chưa chọn mẫu DOCX")
            data = render_docx(download_file(str(key)), context)
            filename, content_type, preview = safe_filename(name, "docx"), DOCX_MIME, None
        elif fmt == "xlsx":
            # Sheets are declarative; `rows` resolves to the real list so numbers stay numbers.
            sheets = _render_args(node_data.get("sheets") or [], state)
            data = render_xlsx(sheets if isinstance(sheets, list) else [sheets], context, title=title)
            filename, content_type, preview = safe_filename(name, "xlsx"), XLSX_MIME, None
        else:
            text = render_markdown(str(node_data.get("template") or "{{ answer }}"), context)
            data = text.encode("utf-8")
            filename, content_type, preview = safe_filename(name, "md"), MARKDOWN_MIME, text
            if node_data.get("set_answer", True):
                state["answer"] = text
    except (ReportError, ValueError) as exc:
        # a bad template or an Excel-illegal sheet title must not kill the whole report run
        state["artifacts"].append({"error": str(exc)})
        state["answer"] = state.get("answer") or f"Không tạo được báo cáo: {exc}"
        return

    artifact = await store_artifact(
        db, workspace_id=workspace_id, data=data, filename=filename, content_type=content_type,
        title=title, kind=str(node_data.get("kind") or "report"),
        audience=("staff" if node_data.get("audience") == "staff" else "admin"),
        run_id=state.get("run_id"), workflow_id=state.get("workflow_id"),
        schedule_id=state.get("schedule_id"), preview=preview,
        created_by_employee_id=state.get("actor_employee_id"),
        created_by_user_id=state.get("actor_user_id"),
        retention_days=node_data.get("retention_days", 30),
    )
    await db.commit()
    state["artifacts"].append({
        "id": str(artifact.id), "filename": artifact.filename, "title": artifact.title,
        "content_type": artifact.content_type, "size": artifact.size,
    })


async def _call_llm(
    provider_name: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    base_url: str | None = None,
    meter: TokenMeter | None = None,
) -> str:
    """Call LLM (non-streaming) and return full response text; ``meter`` gets the reported usage."""
    meter = meter if meter is not None else TokenMeter()
    if provider_name == "google":
        from google import genai
        from google.genai.types import Content, Part

        client = genai.Client(api_key=api_key)
        system_instruction = None
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            else:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append(Content(role=role, parts=[Part(text=msg["content"])]))

        result = client.models.generate_content(
            model=model if model.startswith("models/") else f"models/{model}",
            contents=contents,
            config={
                "system_instruction": system_instruction,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            } if system_instruction else {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        um = getattr(result, "usage_metadata", None)
        if um:
            meter.set(um.prompt_token_count, um.candidates_token_count)
        return result.text or ""

    elif provider_name == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        system = ""
        chat_msgs = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_msgs.append({"role": msg["role"], "content": msg["content"]})

        result = client.messages.create(
            model=model, max_tokens=max_tokens, temperature=temperature,
            system=system, messages=chat_msgs,
        )
        meter.set(result.usage.input_tokens, result.usage.output_tokens)
        return result.content[0].text if result.content else ""

    else:  # openai-compatible (openai / openrouter / vngcloud …)
        import openai
        client = openai.OpenAI(api_key=api_key, base_url=base_url or None, timeout=120)
        result = client.chat.completions.create(
            model=model, max_tokens=max_tokens, temperature=temperature,
            messages=messages,
        )
        if result.usage:
            meter.set(result.usage.prompt_tokens, result.usage.completion_tokens)
        return (result.choices[0].message.content or "") if result.choices else ""
