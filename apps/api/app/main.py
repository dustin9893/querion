from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.deps import close_redis
from app.routers import health, auth, users, workspaces, members, datasets, documents, providers, retrieval, chat, workflows, apps, app_test, tools, staff_auth, employees, public_chat, audit, usage, artifacts, schedules, forms, ops, skills
from app.seed import seed_super_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hooks."""
    # -- Startup --
    await seed_super_admin()
    import asyncio
    from app.services.pii import warm_up
    engine = await asyncio.to_thread(warm_up)  # load Presidio + spaCy once, not on the first chat
    print(f"[pii] masking engine: {engine}")
    # LangGraph checkpoint tables for tool-enabled assistants: before the first request, never inside one.
    from app.services.agent_runtime import setup_checkpointer
    try:
        await asyncio.wait_for(setup_checkpointer(), timeout=60)
    except Exception as e:  # tool assistants report the error; everything else keeps working
        print(f"[agent] checkpoint schema not ready: {e!r}")
    yield
    # -- Shutdown --
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — web dev server locally; production serves web + API on one origin behind Caddy
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(workspaces.router)
app.include_router(members.router)
app.include_router(datasets.router)
app.include_router(documents.router)
app.include_router(providers.router)
app.include_router(retrieval.router)
app.include_router(chat.router)
app.include_router(workflows.router)
app.include_router(apps.router)
app.include_router(app_test.router)
app.include_router(tools.router)
app.include_router(staff_auth.router)
app.include_router(employees.router)
app.include_router(public_chat.router)
app.include_router(audit.router)
app.include_router(usage.router)
app.include_router(artifacts.router)
app.include_router(schedules.router)
app.include_router(forms.router)
app.include_router(ops.router)
app.include_router(skills.router)
