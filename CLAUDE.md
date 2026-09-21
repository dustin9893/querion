# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Querion is now an **internal banking knowledge assistant** (built for the MSB AI Hackathon on a mini-Dify base): multi-unit knowledge bases (datasets → documents → clause-aware chunks → pgvector), a React Flow workflow canvas with a custom DAG runtime, published assistants for **bank staff** and **customers**, and a **compliance audit log** with 👍/👎 feedback. UI is Vietnamese-first. Docs for the hackathon submission: `README.md` (what it is + how to run), `docs/SUBMISSION.md` (the three required deliverables, demo accounts, compliance with the contest rules), `docs/ARCHITECTURE.md` (design decisions and the traps already hit), `docs/PITCH_DECK.md` (slide content), `docs/DEMO_SCRIPT.md` (the demo runbook). Keep the numbers in them in sync when a feature lands.

All demo documents in `apps/api/seed_data/docs/` are **synthetic** (written in MSB vocabulary: EB/RB, RM → CCO1 → CCO2, STEB states, TSBĐ, TTR/MT103). Never copy real internal bank documents into the repo.

Three runnable pieces, all reading the **repo-root `.env`** (copy from `.env.example`):

| Piece | Stack | Port |
|---|---|---|
| `apps/api` | FastAPI, async SQLAlchemy + asyncpg, Alembic | 8000 |
| `apps/worker` | RQ worker (indexing), **sync** SQLAlchemy + psycopg2 | – |
| `apps/api` jobs worker | `python -m app.jobs.worker` — RQ queue `querion-jobs` (reports, forms) | – |
| `apps/api` scheduler | `python -m app.scheduler` — cron ticker for report schedules | – |
| `apps/web` | Next.js 16 (App Router), React 19, Tailwind v4, @xyflow/react | 3000 |
| `apps/extension` | Chrome extension (MV3), Vite + React, reuses the web chat component | – (loaded into Chrome) |

Infra via `infra/docker/docker-compose.yml`: Postgres 16 + pgvector (5432), Redis 7 (**host 6390**), MinIO from quay.io (**host 9010**, console 9011; bucket `querion-docs` auto-created). Host ports were moved off 6379/9000 because other local projects use them; `.env` must say `REDIS_URL=redis://localhost:6390/0` and `MINIO_ENDPOINT=localhost:9010`.

## Commands

```bash
# Infra
cd infra/docker && docker compose up -d && docker compose ps

# API
cd apps/api && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_sm        # spaCy model used by Presidio (PII masking); without it the API falls back to regex
alembic upgrade head
uvicorn app.main:app --reload --port 8000      # GET /health; seeds super admin on startup
python -m app.seed_demo                        # idempotent banking demo data: 4 units, 10 staff, 5 datasets/30 docs, 12 assistants, 25 tools, 7 workflows, 5 schedules, 4 forms, 9 skills
python -m app.reset_demo --yes                 # wipe EVERY business table except ai_providers (+ MinIO bucket, RQ queues), then seed_demo + seed_ops + seed_skills; server: deploy/remote.sh reset-demo (pg_dump first)
python -m app.seed_ops                         # idempotent ops assistant: hidden "Hệ thống" unit, manual, bubble config
python -m app.seed_skills                      # idempotent business skills (seed_demo is marker-gated, this is not)
ruff check app/
pytest tests/ -q                               # unit tests (tests/test_pii.py: Presidio masker, 30 cases, ~1 s)

# Synthetic back-ends for assistant tools (both hosts must be in TOOL_INTERNAL_ALLOWLIST)
./scripts/mock-core.sh                         # demo-mock/core_api.py on :8095 (token demo-core-token)
./scripts/mock-mcp.sh                          # demo-mock/mcp_server.py, MCP streamable-http on :8096/mcp
./scripts/mock-dwh.sh                          # demo-mock/dwh_mcp.py, reporting warehouse over MCP on :8097/mcp
apps/api/.venv/bin/python scratch/smoke_tools.py   # 39 checks: tool CRUD, unit scoping, agent, approval flow
# every scratch suite reads API= and ADMIN_PASSWORD=; smoke_tools and redteam also need port 8095 reachable (they read the mock core directly)
apps/api/.venv/bin/python scratch/smoke_doc_enabled.py  # 19 checks: disabled documents are skipped by retrieval + chat
apps/api/.venv/bin/python scratch/smoke_app_datasets.py # 17 checks: one assistant, several knowledge bases (same env overrides)
apps/api/.venv/bin/python scratch/smoke_usage.py        # 18 checks: token metering per component, summary API, audit tokens, owner scoping
apps/api/.venv/bin/python scratch/smoke_reports.py      # 25 checks: report workflow end to end (needs the jobs worker)
apps/api/.venv/bin/python scratch/smoke_schedules.py    # 28 checks: cron, ticker, run-now, staff delivery (needs the scheduler)
apps/api/.venv/bin/python scratch/smoke_forms.py        # 32 checks: form prefill, AI draft without PII, .docx export
apps/api/.venv/bin/python scratch/smoke_xlsx_report.py  # 20 checks: MCP warehouse → multi-sheet .xlsx (needs ./scripts/mock-dwh.sh)
apps/api/.venv/bin/python scratch/smoke_chat_reports.py  # 14 checks: asking the assistant for a report, the file chip, staff inbox scoping
apps/api/.venv/bin/python scratch/smoke_export.py       # 36 checks: generic Excel export from chat context, number coercion, sheet-name and formula guards
apps/api/.venv/bin/python scratch/smoke_extension.py    # 25 checks: extension channel, assistant filtering, 403 when the flag is off, audit
apps/api/.venv/bin/python scratch/smoke_ops.py          # 39 checks: ops bubble, super-admin-only config, manual citations, workflow drafted → created → RUN → deleted
apps/api/.venv/bin/python scratch/smoke_skills.py       # 42 checks: slug/description rules, overlap warning, activation, SKILL.md round trip, chip in a real answer
apps/api/.venv/bin/python scratch/smoke_memory.py       # 32 checks: three guard layers under attack, read-back, isolation between staff, both switches
apps/api/.venv/bin/python scratch/smoke_demo_data.py    # ~45 checks: the standard seed end to end — counts, unit scoping, one tool question per unit, ```chart in answers, incident triage, 4 Excel reports with charts, form prefill (needs the 3 mocks + jobs worker)
apps/api/.venv/bin/python scratch/smoke_extension.py    # 25 checks: staff JWT `client` claim, extension-only assistant list, 403, audit channel, extension_hosts validation

# Browser extension (see apps/extension/README.md)
cd apps/extension && npm install && npm run build      # → dist/ (API_ORIGINS / VITE_DEFAULT_API_BASE bake the API in); load unpacked in chrome://extensions
EXTENSION_DEMO_HOSTS=localhost:8092 python -m app.seed_demo   # adds the e2e intranet page to the credit assistant's extension_hosts
cd apps/web && npx playwright test e2e/extension.spec.ts       # loads dist/ into Chromium; needs the build + the seed above

# Background jobs for reports / forms, and the schedule ticker (both from the API venv)
cd apps/api && .venv/bin/python -m app.jobs.worker        # RQ queue querion-jobs
cd apps/api && .venv/bin/python -m app.scheduler          # cron ticker, 30s, + artifact cleanup

# Worker (required for indexing; needs an active embedding provider)
cd apps/worker && python -m venv .venv && .venv/bin/pip install -r requirements.txt
./scripts/start.sh                             # or: OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES .venv/bin/python -m worker.main

# Web
cd apps/web && npm install && npm run dev
npm run build && npm run lint                  # lint has pre-existing no-explicit-any errors; build does not run eslint
```

**Alembic gotchas:** `alembic/env.py` overrides the `sqlalchemy.url` in `alembic.ini` with `settings.DATABASE_URL`, so migrations follow `.env` (and the server's env). Migrations are hand-numbered; the chain is 0001 → … → 0020 (0005 creates conversations/messages, 0013 the banking rename, 0014 audit + feedback, 0015 provider base_url, 0016 embed widget, 0017 assistant logo, 0018 conversations.user_id, 0019 employees.workspace_id + apps.share_scope, 0020 tools/app_tools/tool_approvals + apps.agent_enabled, 0021 documents.enabled/disabled_at/disabled_by, 0022 app_datasets replaces apps.dataset_id, 0023 token_usage, 0024 artifacts, 0025 schedules, 0026 form_templates, 0027 apps.extension_enabled/extension_hosts, 0028 apps.system_key + workspaces.is_system + ops_config, 0029 skills/app_skills + apps.skill_match_threshold, 0030 memories + conversations.summary + memory switches on apps/workspaces, 0031 employees.memory_paused). Next is 0032. The LangGraph Postgres checkpointer creates its **own** tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`) via `agent_runtime.setup_checkpointer()`, run in the API lifespan and by `deploy/remote.sh` after Alembic; they are outside Alembic. **Never call `setup()` from a request**: its `CREATE INDEX CONCURRENTLY` waits for every open transaction, including the request's own session (left open by retrieval), and hangs forever (this froze the first tool chat on the server). `setup_checkpointer` also drops invalid `checkpoint*` indexes left by a cancelled build. `alembic/env.py` imports `app.models`, so a new model must be exported from `app/models/__init__.py`. 0013 uses `ADD COLUMN IF NOT EXISTS` for `ai_providers.purpose` because legacy DBs added it by hand.

## Architecture

### Three identity tiers

1. **Admin users** (`users`, `role` = `super_admin` | `admin`) — JWT via `/v1/auth/*`; web keeps the access token in memory and the refresh token in localStorage (`AuthProvider.tsx`). `super_admin` is seeded from `SUPER_ADMIN_*` env (default `admin@querion.io` / `admin123`) and bypasses workspace checks; it is usually a member of **no** workspace, so `AuthProvider` auto-selects the first unit from `GET /v1/workspaces` on login/restore (otherwise no `X-Workspace-Id` header is sent and every unit-scoped call fails with 400 "Chưa chọn đơn vị làm việc"). `admin` is scoped by `user_workspaces.ws_role`: `viewer` < `editor` < `owner`. Memberships are managed on `/admin/users` (super admin: assign a unit + role per user, change role, remove — calls `/v1/workspaces/{id}/members` with an **explicit** `X-Workspace-Id` of the target unit, because the auto-injected header is the super admin's currently selected unit). `GET /v1/users` returns each membership with `workspace_name`.
2. **Employees / bank staff** (`employees`: email, name, `employee_code`, `branch`, `department`, `position` RM|CA|GDV|OPS|CCO|KSV, **`workspace_id`** = their unit, 0019) — separate login `/v1/staff/login`, JWT `role: "staff"`, `require_staff` in `routers/staff_auth.py`. The login body may carry `client` (`portal` default | `extension`); it is stamped into the access **and** refresh token and read back by `staff_client()`, so the server, not a header, knows which surface a session belongs to (see "Browser extension"). **Unit scoping**: `GET /v1/staff/apps` and `POST /v1/staff/apps/{id}/chat` only allow assistants whose `workspace_id` equals the employee's unit **or** whose `apps.share_scope = "bank"` (`_staff_can_use`); an employee with no unit sees only bank-wide assistants. Admins assign the unit on `/admin/employees` (select in the table, `PATCH /v1/employees/{id}`), on create, or via the CSV `unit` column (workspace name/id; blank → the importing admin's `X-Workspace-Id`). **Who manages staff** (`routers/employees.py:staff_scope`): super admin → everyone (`?workspace_id=` filters); a workspace **owner** → only employees of units they own (list needs `X-Workspace-Id`/`?workspace_id`, other units' staff are 404, creating/moving into another unit is 403, CSV rows for other units are rejected); editors/viewers get 403. The web page follows the active unit for non-super admins and hides the unit selects; the sidebar shows "Cán bộ" and "Nhật ký truy vấn" to owners (`Sidebar.tsx` `ownerOk`). Web portal `src/app/staff/*` with its own token keys (`lib/api/staff.ts`). Admins manage them at `/admin/employees` and via CSV (`/v1/employees/import-csv`, sample `apps/api/sample_employees.csv`). `must_change_password` forces a change on first login.
3. **Customers** — no account. A published assistant with `audience="customer"` is reachable at `/kh/<app_id>#k=<api_key>`; the page sends the key as `X-App-Key` to `/v1/public/assistants/*` (`routers/public_chat.py`). The key lives in the URL **fragment** so it never reaches server logs.

### Embeddable chat bubble (`/widget.js` + `/embed/[appId]`)

Third-party websites paste `<script src="<web>/widget.js" data-app data-key async>`. The loader (`apps/web/public/widget.js`, vanilla JS) draws the launcher/panel and frames `/embed/<id>#k=<key>&o=<host origin>`; the chat itself runs on **our** origin, so the API never needs CORS for partner sites. Both audiences embed: customer assistants chat with the publishable key; staff assistants show a login form inside the iframe and then use `/v1/staff/*` with a JWT stored in the iframe's (partitioned) localStorage. Controls, in order of strength:
- `src/proxy.ts` sets `Content-Security-Policy: frame-ancestors 'self' <allowed_origins>` per assistant (from `GET /v1/public/assistants/{id}/frame-ancestors`, 30 s cache; unknown → `'self'` only). `next.config.ts` sends `X-Frame-Options: DENY` everywhere else.
- The embed page verifies `ancestorOrigins`/`referrer` against `allowed_origins` from `embed-config`; postMessage protocol `msbka/1` checks exact origins both ways (never `*`).
- API: `X-Embed-Origin` must be allow-listed and `apps.embed_enabled` true (else 403); the run gets `channel="embed"` + `client_origin` for the audit log. `services/ratelimit.py` (Redis fixed window, fail-open) caps public chat per (assistant, IP) and per assistant per day.
- Admin: assistant detail → tab "Nhúng vào website" (allow-list editor, widget config, snippet, preview). `apps.allowed_origins`/`widget_config` are validated in `services/embed.py`. Shared chat UI: `components/chat/AssistantChat.tsx` + `lib/chat/transport.ts` (customer vs staff transport); `/kh` uses the same component.
- Demo: `./scripts/demo-site.sh` serves `demo-site/` (mock bank landing + intranet pages) on :8090; `seed_demo` allow-lists it and writes `demo-site/config.js` (gitignored). Playwright `e2e/embed-widget.spec.ts` also serves :8091 to prove blocking.

### Browser extension (`apps/extension`, 0027)

A Manifest V3 Chrome extension that puts a **floating, draggable staff bubble on every page**. It is the fourth surface for staff assistants next to the portal, the embedded widget and the customer page, and it reuses the web app's chat: `AssistantChat.tsx`, `Markdown.tsx`, `lib/citations.ts` and `lib/chat/transport.ts` are compiled into the extension by Vite with the `@` alias pointing at `apps/web/src` (React must be `dedupe`d or hooks resolve to null; `transport.ts` guards `process` and exposes `configureTransport({apiBase})` because Vite has no `process.env`).
- **Architecture**: `src/content/content.ts` draws the launcher in a closed Shadow DOM, remembers its position per site in `chrome.storage.local`, and frames `panel.html` (a `chrome-extension://` page, `web_accessible_resources` with `use_dynamic_url`). The host page's CSP does not apply to that frame, its storage is the extension's, and the staff token never touches the page. The panel calls `/v1/staff/*` directly under `host_permissions`, so the API needs no CORS. Content ↔ panel talk over postMessage protocol `msbka-ext/1` with exact origins (`lib/bridge.ts`); the panel derives the page origin from `ancestorOrigins`, never from the message. The content script stays out of the web app's own origin, of `disabledHosts` from managed policy, and of pages that already embed `widget.js` (`.msbka-root`). `background.ts` only toggles the bubble from the toolbar icon.
- **Server side**: `apps.extension_enabled` (opt-in, default off) + `apps.extension_hosts` (host patterns, `services/extension.py:validate_hosts`, `*.` prefix and optional port; mirrored in `src/lib/hosts.ts`). Login with `client="extension"` → `GET /v1/staff/apps` lists only opted-in published assistants (plus `extension_hosts` and `primary_color`), `POST …/chat` returns 403 for a non-opted-in assistant, runs get `channel="extension"` and `client_origin` from the `X-Page-Origin` header (audit only, never an access decision), tool approvals resume on the same channel. Enabling it on a customer assistant is a 400. **This is a product/audit control, not a security boundary against the staff member**, who already holds a token; unit scoping and publication stay the boundary.
- **Side Panel** (`permissions: sidePanel`, `side_panel.default_path = panel.html`, `setPanelBehavior({openPanelOnActionClick: true})`): extensions cannot draw over the browser chrome or on `chrome://` pages (New Tab included), so the toolbar icon opens the same panel as a docked Side Panel that exists on every tab. `App.tsx` detects `window.self === window.top` → side-panel mode: page context comes from `chrome.tabs` (active tab url + `get-context` message to the content script, `selection` pushes, `onActivated/onUpdated`), the default assistant waits for that first look (`contextReady`), `X-Page-Origin` is the active tab's origin and there is no close button. The content script reports suppressed pages (`suppressed`/`active` messages) and the service worker shows a "–" badge with the reason. **Side panel and bubble exclude each other**: the panel page holds a `runtime.connect` port named `msbka-sidepanel` while it lives, the worker mirrors open/closed into `chrome.storage.session.sidePanelOpen` (access level `TRUSTED_AND_UNTRUSTED_CONTEXTS` so content scripts can read it), and every content script hides its bubble on `onChanged` and shows it again when the last panel closes.
- **Choosing the assistant** (`src/panel/App.tsx`): page host matching an assistant's `extension_hosts` → last used (`lastAppId`) → the only one → otherwise the picker (grouped by unit, badges "Toàn ngân hàng" / "Mặc định trên trang này"). The header has a switcher and logout. Selecting text on the page shows a chip "Hỏi về đoạn này" that prefills the input (`AssistantChat` prop `prefill`). Unread badge via `onAnswer` while hidden. Tokens refresh on boot and every 5 min (`lib/api.ts:ensureFreshToken`).
- **Config**: `chrome.storage.managed` (`managed_schema.json`: `apiBase`, `brandName`, `disabledHosts`) pushed by Chrome Enterprise policy wins; the options page can override `apiBase` only when no policy is present; the build bakes a default (`VITE_DEFAULT_API_BASE`) and the allowed API origins (`API_ORIGINS`). Distribution in the bank: `ExtensionInstallForcelist` (self-hosted CRX needs domain-joined machines). Admin UI: assistant Cấu hình tab → "Browser extension" toggle + hosts textarea (staff audience only); audit and usage pages know the `extension` channel. `seed_demo` opts in KHDN (hosts = demo-site host + `EXTENSION_DEMO_HOSTS`), Hồ sơ Tín dụng and the router.
- **Tests**: `tests/test_extension_hosts.py` (28), `scratch/smoke_extension.py` (25), Playwright `e2e/extension.spec.ts` (persistent context with `--load-extension`, fixture page `e2e/fixtures/intranet` on :8092 — no snippet, so the bubble must come from the extension).

### Ops assistant (`/v1/ops`, 0028) — the fifth surface

A floating bubble in the **admin console** that answers questions about running *this product*, and
drafts workflows. Every admin sees it; only super admin configures it at `/admin/ops`.

- **It is a normal `apps` row** marked `apps.system_key = "ops_assistant"`, living in a hidden unit
  (`workspaces.is_system`, name "Hệ thống"). That buys the whole pipeline for free: bound datasets,
  RAG with citations, `mask_pii`, `OutputGuard`, `runs` + `run_steps`, token metering, the agent.
  **`GET /v1/workspaces` filters `is_system` out** — the web auto-selects the first unit for a super
  admin, so leaving it in lands them in an empty unit and every page looks broken.
- **Three kinds of knowledge, three delivery paths** (`services/ops.py`): *how to* comes from the
  "Cẩm nang vận hành" dataset by retrieval; the **node catalogue** (`workflow_schema.prompt_block()`)
  and the unit's **live datasets/tools/workflows** (`ops.context_block`) are **injected into the
  prompt**, never retrieved — a schema must be exact and retrieval returns approximate chunks.
- **Two permission scopes, deliberately separate** (`OpsActor`): `member` (any workspace role) gates
  *configuration* listings, matching what the admin already sees in the UI; `owned` gates
  *audit-like* data, matching `routers/audit.py`. Merging them widens one or strangles the other.
  `X-Workspace-Id` on `/v1/ops/chat` only says which unit is open; it never grants anything.
- **Tools** (`services/tools/ops_tools.py`) are built only when `build_bound_tools(..., ops_ctx=)`
  gets an actor, so a business assistant can never reach them. All read-only:
  `trang_thai_he_thong`, `van_ban_loi`, `luot_hoi_loi`, `token_da_dung`, plus `doc_luong_xu_ly` and
  `soan_luong_xu_ly`. **No write tool at any layer** — the assistant drafts and points, the human clicks.
- **Model override**: `apps.model_config_json["model"]` now actually works (`chat.model_for_app`,
  threaded through `_stream_provider`, `_metered_answer`, `record_usage(model=)` and
  `agent_runtime.build_chat_model`). The ops assistant runs on `z-ai/glm-5.2-hackathon` because
  drafting a workflow is structured-JSON work the everyday chat model does poorly.
- Channel `ops` in `audit.CHANNELS`. Config lives in `ops_config` (one row, fixed id): `enabled`,
  `audience_roles`, `tips`, cadence caps, `workflow_gen_enabled`. Seed: `python -m app.seed_ops`,
  idempotent, run on **every** deploy by `remote.sh`; it only creates what is missing and never
  overwrites what super admin edited, but it does re-upload manual documents whose bytes changed.
- Web: `components/ops/{OpsBubble,OpsTip,WorkflowDraftCard}.tsx` mounted once in `AppShell`, hidden
  on `/login`, `/staff`, `/kh`, `/embed` and `/chat` (that page is already a full-page chat).
  `AssistantChat` gained a generic `renderExtra` slot and a `workflow_draft` SSE event.
- Tests: `tests/test_workflow_schema.py`, `tests/test_workflow_gen.py`, `tests/test_ops_config.py`,
  `scratch/smoke_ops.py` (39), Playwright `e2e/ops-bubble.spec.ts`.

### Workflow node catalogue (`services/workflow_schema.py`, `workflow_gen.py`)

`validate_graph` only ever checked graph **structure**; it never read `node["data"]`, so a `retrieve`
node with no `dataset_ids` passed and died at runtime. `NODE_SPECS` is now the single source of truth
for every node's `data` fields, feeding four consumers: `validate_node_data()` (runs on AI-made *and*
hand-drawn graphs), the prompt block, the canvas property panel, and the manual.
`tests/test_workflow_schema.py::test_seed_graphs_pass` forces every `seed_demo` graph through it, which
is the tripwire against the catalogue drifting from the runtime. Watch out: `parameter_extract.schema`
is a **flat `{name: description}` map, not JSON Schema**.

**The model lists steps; the server draws the graph** (`workflow_gen.steps_to_graph`). Asking a model
for React Flow JSON means asking it to invent consistent ids, edge order and x/y coordinates — three
places to fail. It emits `{"buoc": [{"loai": ...}]}` with `neu_dung`/`neu_sai` for branches; the server
adds input/output, assigns ids, lays out lanes so nothing overlaps, and **emits the true branch edge
first** because the runtime reads edge order, not `sourceHandle`. Validation errors name the step the
model wrote, not the server's node id, so the agent's own tool loop is the repair loop.
`graph_to_steps` goes the other way for editing an existing workflow.

### Skills (`/v1/skills`, 0029) — playbooks loaded on demand

`system_prompt` is always sent, so every playbook added there is paid for by every question, relevant
or not. A skill is the same knowledge with a condition attached: the model always sees each skill's
`name` + `description` (~80 tokens a line) and reads the `body` only when the question matches. That
is the Agent Skills progressive-disclosure idea, and the slug/description limits follow the open spec
so a skill **exports to a `SKILL.md` folder and imports back**.

- **Two activation paths, one per assistant kind.** Agent assistants get an internal tool
  `kich_hoat_ky_nang` (`services/tools/skill_tool.py`, built from the bound skills, capped at 2 reads
  per turn) and decide for themselves. RAG-only assistants have no tool loop, so the server
  **preselects**: `skills.preselect` embeds the question, takes the best cosine against each
  `description_embedding`, and only fires above `apps.skill_match_threshold` (0.32). Below it no skill
  is used at all — answering with no playbook beats answering with the wrong one.
- **The description is the whole game.** `score_description` grades it in the editor,
  `find_overlaps` warns when two skills in a unit describe the same thing (cosine ≥ 0.86), and
  `POST /v1/skills/try` runs a real question through the picker before the skill is bound anywhere.
- **A skill must not contain regulation numbers.** Figures belong in documents so they can be cited;
  copied into a skill they go stale silently when the regulation changes. The editor says so and the
  seeded skills are written that way.
- An active skill narrows retrieval: `preferred_dataset_ids` picks the knowledge bases
  (`chat.skill_dataset_ids`). `skills.allowed_tool_ids` is **stored but not enforced** and is hidden
  from the editor — LangGraph binds an agent's tools statically for the whole turn while the skill is
  chosen mid-turn, so there is no moment at which to narrow them. The column is kept for a future
  design; do not describe it as a control. `reference_document_ids` is provenance for Compliance
  (shown as "dựa trên N văn bản"), not a retrieval filter.
- Lifecycle like a document: `draft|published`, version, `effective_from`, `created_by`/`approved_by`.
  Only published skills are used. `share_scope=bank` and `allow_customer` need **owner**, same as tools.
  Chip `🎯` under the answer in both chat surfaces; `run_steps` gets `skill_activate` with the score.
- Seed: `python -m app.seed_skills` (9 skills across EB/RB/OPS/Legal), **run on every deploy** by
  `remote.sh` — `seed_demo` is marker-gated and would never reach an already-seeded server.
- Tests: `scratch/smoke_skills.py` (42), Playwright `e2e/skills-memory.spec.ts`.

### Personal memory (`/v1/staff/memory`, 0030)

The assistant remembers **how a staff member works**, never what it learned about a customer or a
regulation. Memory belongs to the **employee**, shared across every assistant they can use; the
per-assistant switch is `apps.memory_enabled`, the per-unit one is `workspaces.memory_enabled` +
`memory_retention_days`.

- **No org-level learned memory, on purpose.** If the assistant learned from everyone and replayed it
  to everyone, one staff member's mistake becomes tomorrow's "fact" with no citation and no approver.
  What a unit wants remembered goes in a **document** or a **skill** — both versioned and approved.
- **Four categories only** (`services/memory.py:CATEGORIES`): `trinh_bay`, `vai_tro`, `boi_canh`
  (by business code, 30-day TTL), `thuat_ngu`. Everything else is refused.
- **Three guard layers, and they are code, not prompt wording** (`rejection_reason`): a leftover
  `mask_pii` placeholder, then the category allowlist, then patterns for amounts, named people,
  business outcomes and regulation content. `tests/test_memory_guard.py` holds one case per forbidden
  example; add the test before relaxing a rule.
- **Extraction is structured output** (`_structured_extract` → `with_structured_output(..., include_raw=True)`
  via `build_chat_model`), which pins the category enum at generation time; providers LangChain cannot
  wrap fall back to `chat._call_json_model` + tolerant JSON parsing. The schema fixes the *shape*, not
  the *choice*, so the three guards still run afterwards.
- Extraction runs **in-request after the answer is saved**, not in the background, so the UI can show
  `🧠 Đã ghi nhớ … · Hoàn tác` right under the answer. Cost is ~700 tokens a turn, billed to
  `memory_extract`; embeddings to `memory_embedding`.
- Reads: pinned rows always, plus the 5 closest by cosine, wrapped in a block that states it is **not**
  a source about regulations. `run_steps` records `memory_read` / `memory_write` so Compliance sees the
  personalisation in the audit drawer.
- **Customers get no long-term memory** — they have no account, and Luật Bảo vệ dữ liệu cá nhân
  91/2025/QH15 (in force 01/01/2026) grants access/correction/erasure rights an anonymous person cannot
  exercise. Deactivating an employee erases their memory (`routers/employees.py`), and the scheduler
  sweeps expired rows next to expired artifacts.
- Web: `/staff/memory` "Trợ lý nhớ gì về tôi" (view, edit, pin, delete, **pause separate from
  clear-all**), the undo line in `staff/chat`, and the toggle on the assistant's Kỹ năng tab.
- Tests: `tests/test_memory_guard.py` (30), `scratch/smoke_memory.py` (32).

### Workspace = business unit (Đơn vị)

Workspace-scoped endpoints depend on `require_ws_role(WsRole.x)` from `app/auth/deps.py`, which reads the **`X-Workspace-Id` header** (required, no query-param fallback), checks membership and returns a `WorkspaceContext`; queries must still filter by `ws_ctx.workspace_id`. The web client injects the header in `lib/api.ts` once `setActiveWorkspaceId` is called. Resources carrying `workspace_id`: datasets, workflows, apps, conversations, runs.

### Domain model additions (banking)

- `datasets.visibility` = `internal` | `public`. Customer assistants may only bind `public` datasets; enforced in `routers/apps.py:_validate_audience` on create/update (every bound dataset; the 400 names the internal ones).
- **Several knowledge bases per assistant** (0022): `app_datasets(app_id, dataset_id, position)` replaced `apps.dataset_id` (the migration copied existing bindings). API field `dataset_ids` (list, order kept, max 10) on create/update/response; `_set_datasets` only accepts datasets of the assistant's own unit; deleting a dataset cascades the binding. Every single-assistant response goes through `_full_response` (tool_ids + dataset_ids), list uses one batched query. Assistant conversations no longer set `conversations.dataset_id` (the admin dataset-chat list also filters `app_id IS NULL`). Web: `components/datasets/DatasetPicker.tsx` (checkbox list, internal ones disabled for customer audience) on the create modal and the Cấu hình tab; a workflow-bound assistant ignores them (its nodes pick datasets).
- `documents.doc_type` (`quy_trinh|quy_dinh|huong_dan|san_pham|bieu_phi|mau_bieu|faq`), `version`, `effective_from` — set on upload (multipart form fields) or `PATCH /v1/documents/{id}`; surfaced in every citation.
- `documents.enabled` (0021, default true) + `disabled_at`/`disabled_by`: `PATCH /v1/documents/{id}` `{enabled}` (editor). A disabled document keeps its file and chunks but the single retrieval query (`services/retrieval.py`, `AND d.enabled`) skips it, so every answer path (staff/customer/embed/admin test, workflow `retrieve`, agent, `POST /v1/retrieval`) stops using it at once; re-indexing or editing metadata does not re-enable it. Web: column "Dùng cho AI" (`components/ui/Toggle.tsx`) on the dataset page.
- `apps.audience` = `staff` | `customer`; `apps.api_key` authenticates the customer page. Staff portal lists only `is_published AND audience != customer` **and** (own unit or `share_scope = "bank"`). Each item carries `suggestions` (≤4) and `greeting` from `effective_widget(app.widget_config)`, so the staff portal's suggestion chips and greeting are the ones configured on the assistant (tab "Nhúng vào website"), not hardcoded.
- `apps.share_scope` = `unit` (default) | `bank` (0019): "Phạm vi hiển thị" on the assistant's Cấu hình tab (staff audience only). Changing it requires the workspace **owner** role (`routers/apps.py:update_app` → 403 otherwise; the web sends `share_scope` only when it changed so editors can still save). `seed_demo` opens "Trợ lý Tuân thủ" and the router "Trợ lý Tổng hợp (định tuyến)" bank-wide and puts rm.an/ca.binh in EB, gdv.cuong/ops.hoa/ksv.linh in OPS, rm.dung in RB (the seed re-applies these scopes on every run).
- **Assistant logo**: `apps.logo_key/logo_content_type/logo_updated_at` (0017). `POST /v1/apps/{id}/logo` (multipart, editor) → `services/branding.py:store_logo` validates with Pillow and re-encodes rasters as PNG ≤ 512 px, or keeps a script-free SVG (regex + defusedxml; DOCTYPE/ENTITY/href/url() to outside rejected). `DELETE /v1/apps/{id}/logo` removes it. Served **without a key** by `GET /v1/public/assistants/{id}/logo?v=<ts>` (1-day cache, nosniff, sandboxing CSP for SVG). Every response that describes an assistant carries an API-relative `logo_url` (admin `AppResponse`, public info, `embed-config`, staff `/v1/staff/apps`); the web prefixes it with `apiAssetUrl()` (`lib/api.ts`) or `assetUrl()` (`lib/chat/transport.ts`). Shown by `AssistantChat` (`logoUrl` prop), the widget launcher (`widget.js` receives `logo_url` in the `ready` message), the admin cards and the staff portal. `seed_demo` uploads `seed_data/branding/*.svg` for the two embeddable demo assistants.
- `runs` (+ `run_steps`) are the **audit log**: status `running|queued|completed|failed|blocked|waiting` (waiting = paused for a tool approval, queued = report waiting for the jobs worker), `channel` (`staff|customer|admin_test|embed|extension|ops|report|scheduled|form`; the audit `channel` query filter is built from `audit.CHANNELS`), `workspace_id`, `employee_id`/`user_id`, `query_preview`, `answer_preview`, `error`, `latency_ms`. `messages.run_id` links the saved answer to its run.
- `message_feedback`: one 👍/👎 + optional reason per assistant message (unique on `message_id`).

### Indexing pipeline (API → Redis → worker)

Upload (`POST /v1/datasets/{id}/documents/upload`, `.pdf/.docx/.txt`) stores the file in MinIO, creates a `documents` row and **auto-enqueues** `worker.tasks.index_document.index_document` on RQ queue `querion-indexing`; `POST /v1/documents/{id}/index` re-triggers. Status: `uploaded → indexing → ready | failed`. `seed_demo.py` uses the same path.

Worker steps: download → parse (pdfplumber / python-docx / plain) → **clause-aware chunk** → embed → replace chunks + embeddings → mark ready. `worker/pipeline/chunker.py` first splits on `Chương / Mục / Điều / 1. / 1.1` headings, then windows each section (1000 chars, 200 overlap) and prefixes every chunk with `[breadcrumb]`, e.g. `[CHƯƠNG II … › Điều 5. Phê duyệt tín dụng]`. `retrieval.py:_section_of` parses that prefix back into `section` for citations; the web helper `lib/citations.ts:sourceLabel` renders "văn bản · hiệu lực … · Điều …".

Worker logging: `WORKER_LOG_LEVEL` (default `INFO`); `pdfminer`/`pdfplumber`/`httpx`/`httpcore`/`urllib3`/`openai` are pinned to WARNING in `worker/main.py` because pdfminer at DEBUG writes hundreds of thousands of lines per PDF (a 1.3 MB, 8-page PDF took 36 s to parse instead of 0.7 s). The dataset page polls `GET /v1/documents/{id}` every 3 s while a document is `indexing`.

**Embedding dimension is fixed at 1536** (`vector(1536)`); Google 768-d vectors are zero-padded on both index and query side. Changing the embedding model does not re-index existing chunks.

### AI providers

`ai_providers` rows have `purpose` = `embedding` | `llm` and an optional `base_url`; the first active one per purpose is used. Keys are Fernet-encrypted with `ENCRYPTION_KEY` (shared by API and worker). `provider_name` in {`openai`, `openrouter`, `vngcloud`, `openai_compatible`} all use the OpenAI SDK with `base_url` (defaults per provider in `app/models/model_registry.py:PROVIDERS`); `google` and `anthropic` use their own SDKs. The hackathon setup is **embedding = OpenRouter `openai/text-embedding-3-small`** (1536-d) and **LLM = GreenNode MaaS (VNG Cloud) `google/gemma-4-31b-it`** (the MaaS endpoint exposes only chat models, no embeddings). Reasoning models' `reasoning_content` deltas are ignored by `_stream_openai`. Without an active LLM the chat endpoints still work and emit an `error` SSE event, and a `failed` run is still recorded. `seed_demo.py` can create providers from `SEED_LLM_*` / `SEED_EMBEDDING_*` env.

### Safety layers (code-level, model-independent)

- `services/pii.py:mask_pii` runs on every user message in all channels before LLM / storage / audit (`_preview` masks again). SSE emits `{"type":"notice", "masked": [kinds]}` so the UI shows a 🔒 hint. Engine = **Microsoft Presidio** (`PII_ENGINE=presidio`, default): `AnalyzerEngine` with spaCy `en_core_web_sm` (tokenizer + lemma context only, no NER), built-in `EmailRecognizer`/`CreditCardRecognizer`/`PhoneRecognizer(region VN)` plus custom `PatternRecognizer`s with Vietnamese context words — `VN_ID_NUMBER` (CCCD 12 digits, CMND 9, passport), `VN_BANK_ACCOUNT` (bare ≥10-digit runs, grouped digits), `VN_CIF`, `OTP_CODE`, and a VN mobile pattern for `PHONE_NUMBER`; threshold 0.4, low-score patterns only fire next to context words (`cccd`, `stk`, `otp`, `mật khẩu`…). `AnonymizerEngine` replaces spans with the Vietnamese placeholders in `PLACEHOLDER`; `KIND_OF` maps entity → kind (`email|card|phone|otp|id|account|cif`) for `notice_for`. Digit patterns use `(?<![\d.,/-])…(?![.,/-]?\d)` so amounts (`500.000.000`), dates and document codes (`1234/QĐ-MSB`) survive but a trailing comma does not hide a number. The engine is built once (`warm_up()` in the `main.py` lifespan, ~1 s) and falls back to the regex masker (`_mask_regex`) if Presidio or the spaCy model is missing; `PII_ENGINE=regex|off` forces a mode.
- `services/guard.py`: `OutputGuard` (hold back 160 chars, abort on system-prompt leak signatures → run status `blocked`, generic error to client) wraps every streamed answer via `chat._guarded`; workflow answers are checked whole. `sanitize_chunk` strips markdown images / HTML / "dành cho trợ lý AI" lines from retrieved text, and `_format_context` wraps chunks in `<<<TÀI LIỆU n … >>>` data blocks.
- Prompts explicitly mark context + question as data and forbid revealing the rules. `Markdown.tsx` never renders images. `scratch/redteam.py` is the regression suite (creates and deletes an injected document).

### Answer paths (all go through `services/chat.py`)

LangGraph is used **only** by the tool-calling agent (`services/agent_runtime.py`, see "Tools & agent runtime"); the workflow canvas runtime is still the hand-written `services/workflow_runtime.py`. Every path creates a `Run` via `services/observability.py` and passes it down so steps are logged. Staff, customer and admin-test chat all call `chat.answer_for_app(..., channel=...)`, which picks the agent when `apps.agent_enabled` and the channel may use at least one bound tool, else `app_answer_stream`.

1. **Staff chat** `POST /v1/staff/apps/{id}/chat` and **customer chat** `POST /v1/public/assistants/{id}/chat` → `answer_for_app` → (agent or) `app_answer_stream(db, app, query, history, collector, run=run)`: MODE 1 app has `workflow_id` → `run_workflow` (whole answer emitted as one token; a `type="report"` workflow is skipped, see "Reports"); MODE 2 bound datasets (`chat.app_dataset_ids`, one or more) → one retrieval across all of them with a global top_k, then stream; MODE 3 plain LLM. The system prompt is `app.system_prompt` if set, else `STAFF_SYSTEM_PROMPT` / `CUSTOMER_SYSTEM_PROMPT` (Vietnamese guardrails: answer only from context, cite `[#n]`, say when the documents don't cover it, never decide credit approvals, never echo customer PII).
2. **Admin dataset chat** `POST /v1/conversations/{id}/messages` → `chat_stream(..., run=run, collector=collector)`.
2b. **Admin test console** (`/chat`, "Thử nghiệm hỏi đáp") → `routers/app_test.py`: `POST /v1/apps/{id}/test-chat` (viewer role + `X-Workspace-Id`, works for unpublished assistants) → `app_answer_stream` like staff/customer, channel `admin_test`, `user_id` on the run; conversations carry `conversations.user_id` (0018) and are excluded from the customer endpoints (`user_id IS NULL`) and the staff portal (`employee_id`). Reload via `GET …/test-conversations/{cid}/messages`, rate via `POST …/test-messages/{mid}/feedback`. Web: `lib/chat/adminTransport.ts` + the shared `AssistantChat` (variant `embed`, widget mirrored from `widget_config`).
3. **Workflow test run** `POST /v1/workflows/{id}/run` → validates, `run_workflow(..., run=run)`, blocking JSON.

**SSE wire format** (parsed by hand in `staff/chat/page.tsx`, `kh/[appId]/page.tsx`, `datasets/[id]/chat/page.tsx`):
```
data: {"type": "conversation_id", "conversation_id": "..."}     # first event (staff/customer)
data: {"type": "sources", "sources": [...]}                     # before tokens; items carry filename/doc_type/version/effective_from/section/score
data: {"type": "tool_call", "tool": "slug", "label": "...", "status": "running"}          # agent only
data: {"type": "tool_result", "tool": "slug", "label": "...", "status": "done|error|rejected"}
data: {"type": "token", "content": "..."}
data: {"type": "error", "content": "..."}
data: [DONE]
data: {"type": "tool_approval", "approval_id": "...", "tool": "...", "label": "...", "args": {...}}   # agent paused; no answer yet, run status "waiting"
data: {"type": "message_saved", "message_id": "...", "run_id": "..."}   # after DONE, once the answer is persisted → enables 👍/👎
data: {"type": "title", "title": "..."}                          # first exchange only
```

### Tools & agent runtime (LangGraph)

- **Registry** (0020): `tools` rows belong to a workspace (`slug` = function name the model sees, unique per unit; `description` = what the model reads; `kind` `http|builtin|mcp|report|export`; `config`; `params_schema` JSON Schema; `secret_encrypted` Fernet; `requires_approval`; `allow_customer`; `share_scope` `unit|bank`; `timeout_sec`). `app_tools` binds tools to assistants; `apps.agent_enabled` switches the assistant to the agent — a tool bound while that flag is off is never called, which looks exactly like a broken tool, so `POST /v1/apps` accepts `tool_ids`/`agent_enabled` (agent defaults on when tools are given) and the web tools tab turns the switch on with the first tick and warns in red if tools are selected while it is off. `routers/tools.py`: list (own unit + bank-shared), CRUD (editor, owning unit only via `_load_own`), `POST /v1/tools/{id}/test` (runs it for real; `_load_usable` also allows active bank-shared tools of other units; schema errors come back as "Tham số không hợp lệ …"; the web dialog pre-fills a template from `params_schema`), `GET /v1/tools/builtins`. Secrets are write-only (`has_secret`). Owner role is required for `share_scope=bank` and `allow_customer`. An assistant may bind only tools of its unit or bank-shared ones; a customer assistant only `allow_customer` tools (`routers/apps.py:_set_tools`), and approval-gated tools are never offered on the customer channel (`registry.app_tool_rows`).
- **Kinds** (`services/tools/`): `http` → `executor.execute_http` (SSRF guard `http_target_blocked`, `{{arg}}` templating that keeps JSON types, secret injected into `secret_header` server-side, timeout, 4000-char cap, `response_path`); `builtin` → pure functions in `builtin.py` (lịch trả nợ, phí %, ngày làm việc, lãi tiền gửi) whose schema comes from `BUILTINS`; `mcp` → one row = one MCP **server**, loaded with `langchain-mcp-adapters` and exposed as `<slug>__<tool>`; stdio transport only when `ENABLE_MCP_STDIO=true` (it launches a process). `TOOL_INTERNAL_ALLOWLIST` (`host` or `host:port`, comma-separated) is the narrow exception to the SSRF guard for internal systems. `report` → one row points at a report workflow (`config.workflow_id`) and `report_args_schema` derives the tool's arguments from that workflow's `input` fields, so the model fills the same form a human would; `_report_callable` runs the workflow on its **own** session, records a run, and returns the summary as a data block with the produced files appended after `ARTIFACT_MARKER` (`executor.attach_artifacts` / `split_artifacts`) — the agent strips that tail, so the model never sees artifact ids. `export` (`services/tools/export.py`) → the **generic** file maker: no workflow and no lookup of its own, its arguments *are* the spreadsheet (`sheets[].{ten,tieu_de,cot[{nhan,khoa,dinh_dang,tong}],dong,tom_tat}`), so the model fills them from what the conversation already holds — a table the user pasted, a tool result, a retrieved passage. The schema is generated by `export_args_schema()` and never author-supplied. `build_sheets` maps it onto `render_xlsx`, coercing model output on the way: Vietnamese and English number strings become numbers (`'412.000.000.000'`, `'1,250,000.50'`), a percent written as `91,6` becomes `0.916`, a row given as an array is matched positionally to the columns, and limits are 5 sheets / 30 columns / 2000 rows / 2000 chars per cell. `reports.py` keeps the workbook buildable whatever the model writes: `safe_sheet_name` rewrites titles Excel refuses (`Doanh số 08/2026` → `Doanh số 08-2026`, ≤31 chars, de-duplicated) and `_put` forces a cell to text when openpyxl would make it a formula or cannot store it at all, so `=HYPERLINK(...)` from a document stays text and a stray dict does not kill the file — both guards cover the workflow reports too. LangChain does **not** enforce a dict `args_schema`, so `registry._validate_args` runs `jsonschema` first.
- **Runtime** (`services/agent_runtime.py`): per request a `StateGraph` `agent ⇄ tools` (not the deprecated `create_react_agent`), model = `langchain_openai.ChatOpenAI` for OpenAI-compatible providers only (google/anthropic → SSE error). Retrieval still runs first when the assistant has a dataset, so citations survive; the system prompt is the audience guardrail prompt + `TOOLS_PROMPT`. `ToolNode(awrap_tool_call=_AgentRun.wrapper())` is the seam: emits `tool_call/tool_result`, records calls (written to `run_steps` as `node_type="tool_call"` after the stream, because the graph must not share the DB session), wraps MCP output with `as_untrusted_block` (http/builtin callables wrap their own) — every tool result reaches the model as `<<<KẾT QUẢ CÔNG CỤ …>>>` data. **Do not set `ToolNode(handle_tool_errors=True)`**: it swallows the `GraphInterrupt` that `interrupt()` raises, silently disabling approvals; errors are caught in the wrapper instead. `ToolNode` hands the wrapper a **`ToolMessage`**, not the callable's string, so `_tool_message_text` / `_replace_tool_text` unwrap it before `split_artifacts` looks for files; each file becomes an `artifact` SSE event and is collected on `AnswerCollector.artifacts`. `build_bound_tools(..., actor_employee_id=, actor_user_id=)` records who asked, so a report a staff member requested is stored under them. Tokens stream via `stream_mode=["messages","updates"]` in a background task into a queue (`_pump`/`_drain`); `OutputGuard` still filters them.
- **Approval** (human-in-the-loop): a `requires_approval` tool calls `interrupt()` before running; `_pump` reads `__interrupt__` from the `updates` stream (do not rely on `aget_state`), sets `collector.pending_approval`; the router writes `tool_approvals` (`services/tools/approvals.record_pending`), sets `runs.status="waiting"` and emits `tool_approval` after `[DONE]`. `POST /v1/staff/tool-approvals/{id}` or `POST /v1/apps/{app}/test-tool-approvals/{id}` `{approve}` → `continue_after_decision` resumes with `Command(resume=bool)` on the **Postgres checkpointer** (`thread_id = run.id`, `AsyncPostgresSaver` on a psycopg pool, singleton `get_checkpointer`), streams the rest, saves the message and completes the run. A decided approval returns 404.
- **PII constraint**: `mask_pii` runs before the model, so CIF, account and ID numbers never reach a tool argument; design tools around non-sensitive business codes (mã hồ sơ, mã phí, mã tiền tệ). The demo data is keyed by file number for that reason.
- **Web**: `/tools` page (`app/tools/page.tsx`, `lib/api/tools.ts`), assistant tab "Công cụ" (toggle + bind), tool chips and the approval card in both `AssistantChat.tsx` and `staff/chat/page.tsx` (`transport.approve` for embed/admin-test). Demo: `seed_demo` creates 20 business tools across EB/RB/OPS (http against `demo-mock/core_api.py`, builtins shared bank-wide incl. `kiem_tra_kha_nang_tra_no` DTI, two MCP servers `he_thong_rui_ro` (bank-wide: xếp hạng, EWS `canh_bao_som`, `sang_loc_cam_van`) and `kho_du_lieu_bao_cao`, two approval-gated writes `gia_han_ho_so` / `phan_cong_khieu_nai`) plus 5 `report` tools; agent assistants per unit: EB "Trợ lý Hồ sơ Tín dụng" + "Trợ lý Thẩm định Tín dụng (CA)", RB "Trợ lý Tư vấn KHCN", OPS "Trợ lý Kiểm soát TTQT" + "Trợ lý Khiếu nại & Tra soát", Legal "Trợ lý Rà soát AML" (bank-wide); the customer assistant gets `tra_ty_gia`, `tinh_lai_tien_gui`, `tra_lai_suat`, `tim_diem_giao_dich`, `tinh_phi_giao_dich`. Tests: `scratch/smoke_tools.py`, `scratch/smoke_demo_data.py`, Playwright `e2e/tools.spec.ts`.

### Reports, forms and schedules (0024–0026)

**Artifacts** — every file a run produces is one `artifacts` row (no FKs: a report outlives the
workflow, schedule or unit that made it) plus an object in MinIO under `reports/<ws>/<id>/`. Bytes
are served only by `GET /v1/artifacts/{id}/download` (unit-scoped) or `/v1/staff/reports/{id}/download`,
so the object store stays private. `expires_at` defaults to 30 days; the scheduler deletes expired rows.

**Report workflows** (`workflows.type = "report"`): the canvas gains two nodes.
- `tool_call` → `registry.run_tool_by_id` (same SSRF guard, secret injection and JSON-Schema check as
  the agent; approval-gated tools are **refused** — a scheduled report has nobody to approve). Works for
  `http`, `builtin` and `mcp` rows; an MCP row is one server, so the node also names `mcp_tool`, and
  `_mcp_payload` unwraps the content blocks (`[{type:"text",text:"<json>"}]`) into real data — without
  that a spreadsheet gets a string instead of rows. Result lands in `state["tool_results"][alias]`, and
  `compose_prompt` wraps it in `<<<KẾT QUẢ CÔNG CỤ …>>>` via `{{tool_results}}` so the model still
  treats it as data.
- `render_document` → three formats, all stored as an artifact: **Markdown** and **`.docx`** (docxtpl)
  rendered by a **sandboxed** Jinja env (`services/reports.py`, filters `| tien | so | ngay`), and
  **`.xlsx`** built from a declarative spec (`render_xlsx`: `sheets[].{name,title,rows,columns,summary}`,
  column `format` money/int/number/percent, `total: true` for a totals row, frozen header, auto width).
  A report is a table, so the spreadsheet is generated, not templated. `vars` maps short template names
  to state paths; `audience: staff` also publishes it to the staff portal.
- An `input` node may declare `fields` (name/label/type/required/options); the runtime validates them
  and the run dialog, schedule editor and staff form all build their form from the same list.
- Reports run off-request: `POST /v1/workflows/{id}/jobs` creates the `runs` row (channel `report`)
  and queues `app.jobs.tasks.run_workflow_job` on **`querion-jobs`**, worked by `python -m app.jobs.worker`
  **from the API image** (it needs the runtime, tools, MinIO and token metering).
- A report workflow **cannot be the brain of an assistant**: `routers/apps.py:_check_chat_workflow` rejects
  binding one (400, pointing at the report tool), and `chat.app_answer_stream` ignores a `type="report"`
  workflow on an assistant bound before that check existed — otherwise "xin chào" would build a report.
  The check compares against the assistant's **current** value and passes when it is unchanged: the web
  page saves the whole assistant at once, so refusing a legacy binding would 400 every save and leave the
  owner unable to tick a tool or clear the workflow (`tests/test_app_workflow_rule.py`). Such a binding is
  shown in the select as "(báo cáo — không dùng cho hội thoại)" so it can be cleared.
  Chat reaches reports through a **tool of kind `report`** instead: the model calls it only when the
  question asks for one, the files come back as `artifact` SSE events, and the chat shows a download button
  **under** the answer, where the model's own wording points (`ChatFile` in `AssistantChat.tsx` and
  `staff/chat/page.tsx`, `transport.downloadFile`; it carries the title, filename and size).
- A report workflow answers one fixed question. For everything else there is the **`export` tool**
  (`xuat_excel`, seeded bank-wide): "xuất cái này ra Excel" turns whatever the conversation holds into an
  `.xlsx` with no workflow behind it. Same artifact plumbing, so the file also lands in the asker's
  "Báo cáo của tôi" (`kind="export"`, `audience="staff"` when an employee asked) and in the audit run.

- **Charts** (`reports.py:_chart_specs/_add_charts`): a sheet may carry `charts: [{type bar|bar_h|line|pie, title, category_field, series:[{field,name}]}]`; they are native openpyxl charts anchored right of the table, referencing **columns of the same sheet by field name** (never cell ranges), max 3 per sheet / 4 series, pie keeps the first series. Bad specs are dropped silently so a scheduled report never loses its table over decoration. The export tool exposes the same as `sheets[].bieu_do {loai cot|cot_ngang|duong|tron, tieu_de, truc_nhan, chuoi[]}` (`export.py:CHART_KINDS`). **Charts in chat** are a different mechanism: `chat.CHART_PROMPT` (appended by `build_system_prompt` for every non-customer audience) asks the model for one ```chart fenced block of JSON `{loai, tieu_de, don_vi, nhan[], chuoi[{ten, gia_tri[]}]}`; `components/ui/ChartBlock.tsx` renders it as pure SVG and `Markdown.tsx` swaps the `language-chart` code block for it (the `pre` wrapper is skipped for that block only). No images, no new dependency, shared by portal/embed/extension. Tests: `tests/test_charts.py`.

**Who sees a file** (`staff_auth._staff_reports_stmt`) — "Báo cáo của tôi" lists exactly two things:
files the employee produced themselves (a form they filled, a report they asked the assistant for,
`artifacts.created_by_employee_id`) and files a **schedule** delivered to them, honouring
`deliver_positions` ([] = every employee of the unit). A report an admin ran by hand from the canvas
has no delivery target, so it stays in the admin UI and never lands in everyone's inbox.

**Schedules** (`schedules`): `python -m app.scheduler` polls every 30s, claims due rows with
`FOR UPDATE SKIP LOCKED`, queues them (channel `scheduled`) and advances `next_run_at` — two tickers
never double-fire and missed slots are skipped, not replayed. Cron is 5-field in `Asia/Ho_Chi_Minh`
(`services/scheduling.py` validates, previews and describes it in Vietnamese). A Redis heartbeat
(`scheduler:heartbeat`) drives the "bộ lập lịch chưa chạy" warning on `/admin/schedules`.
`deliver_positions` filters which positions see the report in the staff portal ([] = the whole unit); it is the
only way a file reaches an employee who did not create it.

**Forms** (`form_templates`): fields have a `source` — `user` (typed), `tool` (prefilled from one
registry tool keyed by a business code) or `llm` (drafted). Fields flagged **`pii` never reach the
model** (`forms.non_sensitive`); that is why filling a form is a UI form and not a chat, where
`mask_pii` would redact exactly the values the document needs. Staff flow: `/v1/staff/forms`,
`…/prefill`, `…/suggest` (records `form_suggest` token usage), `…/submit` → `.docx` artifact
(channel `form`). Admin: `/forms` page — fields table, prefill mapping, `.docx` upload (rejected when
it uses a placeholder no field declares), publish (blocked without a template), test render.

### Workflow runtime

`graph_json` is React Flow shape. `services/workflow_validator.py` enforces known node types (`input, retrieve, compose_prompt, llm_generate, parameter_extract, if_else, http_request, code_execute, tool_call, render_document, answer, output`), exactly one input and one output, max 1 outgoing edge (2 for `if_else`), no cycles. With two `if_else` edges the runtime takes the **first edge as true, second as false**, ignoring `sourceHandle` — edge order in `graph_json` matters. State dict: `query, inputs, retrieved_chunks, prompt_messages, answer, citations, extracted_params, history, http_response, code_output`. `code_execute` is `exec()` with a restricted builtins dict, not a sandbox. `seed_demo.py:_router_graph` is the reference graph (intent classification → branch → retrieve credit|ops → compose → llm).

### Token usage (`services/usage.py`, `routers/usage.py`, 0023)

Every model call writes one `token_usage` row (no FKs on purpose: accounting history outlives deleted assistants/datasets/units): `component` (`answer` RAG/plain answer incl. admin dataset chat · `agent` one row per LangGraph model round · `workflow_llm` / `workflow_extract` workflow nodes · `title` · `query_embedding` · `document_embedding`), `purpose` llm|embedding, `channel` (run channel, or `retrieval_test` / `indexing` / `admin_edit`), `workspace_id`/`app_id`/`run_id`/`dataset_id`/`document_id`, provider + model, prompt/completion/total tokens, `calls`, `estimated`.
- Counts come from the provider: OpenAI-compatible streams ask `stream_options.include_usage` (retried without it if a gateway rejects the option), `ChatOpenAI(stream_usage=True)` gives `usage_metadata` per agent round, Google `usage_metadata`, Anthropic final message usage, embeddings `usage.prompt_tokens`. When nothing is reported the row is estimated at 3 chars/token and flagged. VNG MaaS and OpenRouter both report exact counts.
- API side: `UsageScope.of_run(run)` says who pays; `TokenMeter` is filled by the vendor call; `record_usage` inserts in its **own** session and never raises (metering must not break an answer or join the request transaction). `_metered_answer` in `chat.py` wraps the guarded stream and records in `finally`. `retrieve(..., usage=scope)` / `embed_query(..., usage=, component=)` meter embeddings; `generate_title(..., usage=)`; `_call_llm(..., meter=)`; `_build_graph(..., provider=, usage=)`. Worker: `embed_texts(meter=)` + `index_document._record_usage` (committed right after embedding). The chunk-edit endpoint now re-embeds through `embed_query` (it used to ignore `base_url`).
- `GET /v1/usage/summary?days&workspace_id&app_id&channel&component` → totals, `by_day` (Asia/Ho_Chi_Minh days, every day present, tokens per component), `by_component/purpose/channel/app/workspace/model`. Same access rule as the audit log (`audit._allowed_workspaces`). The audit log gets `total_tokens` per run and `usage` (per component) in run detail.
- Web: `/admin/usage` "Token sử dụng" (sidebar, owners too): period + unit/assistant/channel/component filters, tiles, stacked daily chart, breakdown lists; `lib/api/usage.ts` holds component labels/colours. Audit page: "Token" column + per-component table in the drawer.

### Audit API (`routers/audit.py`)

`GET /v1/audit/runs` (filters: workspace, app, channel, rating up|down|none, status, q, days), `GET /v1/audit/runs/{id}` (question, full answer, citations, steps, feedback), `GET /v1/audit/summary`, `GET /v1/audit/filters`. super_admin sees everything; an admin sees only workspaces where they are **owner**. Web page: `/admin/audit`.

### Web conventions

- Routes: `/login`, `/datasets`, `/workflows`, `/apps`, `/forms`, `/chat` (admin test console), `/skills`, `/admin/{users,workspaces,settings,employees,audit,usage,schedules,ops}` (admin shell via `AppShell`; `Topbar` titles come from the same `nav.*` / `admin.*` keys as the sidebar), `/staff/*` (own layout + `StaffSettingsProvider`: `chat`, `reports` = "Báo cáo của tôi", `forms`, `memory` = "Trợ lý nhớ gì về tôi"), `/kh/[appId]` and `/embed/[appId]` (public, no providers). `AppShell` and `AuthProvider` skip `/staff`, `/kh`, `/embed`.
- i18n is a **custom** `I18nProvider` (`next-intl` installed but unused): `const { t } = useI18n(); t("key", "namespace")`, JSON in `src/locales/{vi,en}/<namespace>.json`, default locale `vi`. Staff portal has its own tiny dictionary in `lib/i18n/staff.ts`. Many admin pages still hardcode Vietnamese strings.
- Brand: `lib/brand.ts` reads `NEXT_PUBLIC_BRAND_NAME` (default "MSB Knowledge Assistant"). Accent colour tokens in `globals.css` (orange `#ee6d1f`).
- API clients in `src/lib/api/*.ts` via `apiFetch` (8 s default timeout; pass `timeout`). Streaming endpoints use raw `fetch` with manual headers.

### Deployment (`deploy/`)

`deploy/deploy.sh` (local) → `git archive HEAD` + `remote.sh` over SSH (port 234, user `stackops`) → `remote.sh deploy` on the server: build images, start infra, **pg_dump backup**, `docker compose run --rm api alembic upgrade head`, `up -d`, then **force-recreate `caddy`, `mock-core`, `mock-mcp`** (they bind-mount files of the release directory; without recreation they stay mounted on the previous release, which the next deploy deletes → demo site 404), seed once. Migrations are no longer in the API image `CMD`; anything that changes data on redeploy must be an Alembic migration. `~/querion/shared/.env` is created once by `remote.sh init-env` and symlinked to `app/deploy/.env` (compose interpolation). The seed writes `demo-site/config.js` to `DEMO_SITE_DIR=/shared/demo-site`, which Caddy serves at `demo.<domain>/config.js`. `alembic/env.py` takes the URL from `settings.DATABASE_URL` (the ini value is only a fallback). In compose the tool mocks are `mock-core:8095` (hồ sơ EB, hạn mức, tỷ giá, biểu phí, lãi suất, điểm giao dịch, hồ sơ KHCN `HSCN2026-010x`, điện SWIFT gpi `TTR2026-xxxx`, khiếu nại `KN2026-030x` + write `phan-cong`), `mock-mcp:8096` (risk: xếp hạng, LTV, EWS, sàng lọc cấm vận với danh sách hư cấu) and `mock-dwh:8097` (reporting warehouse: EB doanh số/nợ/KPI, RB huy động-cho vay, xu hướng 6 tháng, khiếu nại theo loại, TTQT theo ngày), allow-listed via `TOOL_INTERNAL_ALLOWLIST`. **Every figure in them is synthetic**; the mocks are bind-mounted from the release, so a data change needs `--force-recreate` (remote.sh does it). The API runs `uvicorn --proxy-headers` so `X-Forwarded-For` from Caddy feeds rate limits. Web image: Next `output: "standalone"`, `NEXT_PUBLIC_API_URL` passed as a build arg (it is inlined at build time), `API_INTERNAL_URL=http://api:8000` at runtime for `proxy.ts`.

### Config notes

- API `Settings` (`app/config.py`) reads `apps/api/.env` then `../../.env`; the worker reads only the repo-root `.env`. Keep one file. `DEBUG=true` turns on SQLAlchemy echo (very noisy).
- CORS origins come from `CORS_ORIGINS` (comma-separated, default `http://localhost:3000`); in production web and API share one origin behind Caddy.
- Root `.gitignore` ignores any file named `*secret*` / `*credentials*` and `next-env.d.ts`.
- LangGraph entered the code only with the tools agent (0020) and is scoped to that path; the workflow canvas has its own runtime.
- Upgrading to LangGraph pulled `openai` from 2.x to 3.x; `_stream_openai` was verified unchanged against VNG.
