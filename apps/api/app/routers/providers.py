"""Admin endpoints for managing AI provider keys (super_admin only)."""

from uuid import UUID
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.deps import get_current_user
from app.models import AiProvider, User
from app.models.model_registry import MODELS, PROVIDERS, default_base_url
from app.services.encryption import encrypt_key, decrypt_key, mask_key

router = APIRouter(prefix="/v1/admin", tags=["admin-providers"])


# ---------- Schemas ----------

class ProviderCreate(BaseModel):
    provider_name: str = Field(..., max_length=64, examples=["openai"])
    display_name: str = Field(..., max_length=128, examples=["OpenAI Embeddings"])
    api_key: str = Field(..., min_length=1)
    model_name: str = Field(..., max_length=128, examples=["text-embedding-3-small"])
    purpose: str = Field("embedding", examples=["embedding", "llm"])
    base_url: str | None = Field(None, max_length=512, examples=["https://openrouter.ai/api/v1"])


class ProviderUpdate(BaseModel):
    display_name: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    purpose: str | None = None
    is_active: bool | None = None
    base_url: str | None = None


class ProviderResponse(BaseModel):
    id: UUID
    provider_name: str
    display_name: str
    api_key_masked: str
    model_name: str
    purpose: str
    base_url: str | None = None
    is_active: bool
    created_at: str
    updated_at: str


# ---------- Helpers ----------

def _require_super(user: User) -> None:
    if user.role.value != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin only")


def _to_response(p: AiProvider) -> ProviderResponse:
    return ProviderResponse(
        id=p.id,
        provider_name=p.provider_name,
        display_name=p.display_name,
        api_key_masked=mask_key(decrypt_key(p.api_key_encrypted)),
        model_name=p.model_name,
        purpose=p.purpose or "embedding",
        base_url=p.base_url,
        is_active=p.is_active,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


# ---------- Model Registry (public) ----------

@router.get("/models")
async def list_available_models(
    provider: str | None = Query(None),
    purpose: str | None = Query(None),
):
    """List available AI models, optionally filtered by provider and/or purpose."""
    result = MODELS
    if provider:
        result = [m for m in result if m["provider"] == provider]
    if purpose:
        result = [m for m in result if m["purpose"] == purpose]
    return {"providers": PROVIDERS, "models": result}


# ---------- Provider CRUD ----------

@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_super(user)
    result = await db.execute(select(AiProvider).order_by(AiProvider.created_at.desc()))
    return [_to_response(p) for p in result.scalars().all()]


@router.post("/providers", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: ProviderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_super(user)
    provider = AiProvider(
        provider_name=body.provider_name,
        display_name=body.display_name,
        api_key_encrypted=encrypt_key(body.api_key),
        model_name=body.model_name,
        purpose=body.purpose,
        base_url=(body.base_url or "").strip() or default_base_url(body.provider_name),
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return _to_response(provider)


@router.patch("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: UUID,
    body: ProviderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_super(user)
    result = await db.execute(select(AiProvider).where(AiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if body.display_name is not None:
        provider.display_name = body.display_name
    if body.api_key is not None:
        provider.api_key_encrypted = encrypt_key(body.api_key)
    if body.model_name is not None:
        provider.model_name = body.model_name
    if body.purpose is not None:
        provider.purpose = body.purpose
    if body.is_active is not None:
        provider.is_active = body.is_active
    if body.base_url is not None:
        provider.base_url = body.base_url.strip() or None

    await db.commit()
    await db.refresh(provider)
    return _to_response(provider)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_super(user)
    result = await db.execute(select(AiProvider).where(AiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    await db.delete(provider)
    await db.commit()
