# Smoke / E2E scripts

Run against a live stack (API :8000, worker, providers configured) from `apps/api` with its venv:

```bash
cd apps/api && source .venv/bin/activate
python ../../scratch/smoke_apps_staff.py   # audience/visibility rules, staff portal, SSE envelope (no LLM needed): 20
python ../../scratch/smoke_audit.py        # runs + feedback + audit scoping (no LLM needed): 15
python ../../scratch/e2e.py                # full flow with real embedding + LLM: 67 checks
python ../../scratch/redteam.py            # 22 adversarial scenarios (needs ./scripts/mock-core.sh)
python ../../scratch/smoke_tools.py        # tools registry, unit scoping, agent + approval (needs ./scripts/mock-core.sh): 39
python ../../scratch/smoke_doc_enabled.py  # disabled documents are skipped by retrieval and chat: 19
python ../../scratch/smoke_app_datasets.py # one assistant bound to several knowledge bases: 17
python ../../scratch/smoke_usage.py        # token metering per component + /v1/usage/summary: 18
python ../../scratch/smoke_reports.py      # report workflow: tool_call + render_document + background job: 25
python ../../scratch/smoke_schedules.py    # cron schedules, ticker, staff delivery: 28
python ../../scratch/smoke_forms.py        # business forms: prefill, AI draft without PII, .docx: 32
python ../../scratch/smoke_xlsx_report.py  # MCP warehouse → multi-sheet Excel report: 20
python ../../scratch/smoke_export.py       # generic Excel export from chat context: 36
python ../../scratch/smoke_chat_reports.py # asking the assistant for a report, staff inbox scoping: 14
python ../../scratch/smoke_extension.py    # browser-extension channel, assistant filtering, audit: 25
python ../../scratch/smoke_skills.py       # skills: slug/description rules, overlap, activation, SKILL.md round trip: 42
python ../../scratch/smoke_memory.py       # personal memory: three guard layers under attack, isolation, switches: 32
python ../../scratch/smoke_ops.py          # ops assistant: config is super-admin only, manual citations, a drafted workflow is created, RUN and deleted: 39
python ../../scratch/smoke_demo_data.py    # the standard seed as the jury sees it: counts per unit, unit scoping, one tool question per unit, charts in chat, incident triage branches, 4 Excel reports with real charts, form prefill (needs all three mocks + jobs worker): ~45
```

## Pointing a suite at another host

Every suite reads `API` and `ADMIN_PASSWORD` from the environment:

```bash
API=https://<domain> ADMIN_PASSWORD=<super admin password> python ../../scratch/e2e.py
```

Two suites also call the mock core API **directly** to compare state before and after a write, so
they only run where port 8095 is reachable: `smoke_tools.py` (its `MOCK_CORE` env var moves the URL
the API is told to call) and `redteam.py`. The other 16 run unchanged against a deployment.

`e2e.py` takes the embed origin from the assistant's own allow-list, so it works both with the local
demo site on :8090 and with a deployed `demo.<domain>`; `EMBED_ORIGIN` overrides it.
