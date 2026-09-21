"""Generate embeddings via OpenAI or Google API. Reads API key from DB (encrypted)."""

import openai
from cryptography.fernet import Fernet

from worker.config import ENCRYPTION_KEY

# pgvector column is vector(1536) — all embeddings must be this size
TARGET_DIM = 1536


def _decrypt(ciphertext: str) -> str:
    """Decrypt API key using Fernet."""
    return Fernet(ENCRYPTION_KEY.encode()).decrypt(ciphertext.encode()).decode()


def _pad_to_target(vectors: list[list[float]]) -> list[list[float]]:
    """Zero-pad vectors shorter than TARGET_DIM (e.g. Google 768d → 1536d)."""
    result = []
    for v in vectors:
        if len(v) < TARGET_DIM:
            v = v + [0.0] * (TARGET_DIM - len(v))
        result.append(v[:TARGET_DIM])  # also truncate if somehow longer
    return result


def embed_texts(
    texts: list[str],
    api_key_encrypted: str,
    model_name: str = "text-embedding-3-small",
    provider_name: str = "openai",
    batch_size: int = 100,
    base_url: str | None = None,
    meter: dict | None = None,
) -> list[list[float]]:
    """Embed a list of texts using the specified provider.

    All vectors are normalized to TARGET_DIM (1536) dimensions. ``meter`` (optional dict) receives
    ``calls`` and, when the provider reports it, ``tokens``.
    """
    api_key = _decrypt(api_key_encrypted)
    meter = meter if meter is not None else {}
    meter.setdefault("calls", 0)

    if provider_name == "google":
        raw = _embed_google(texts, api_key, model_name, batch_size, meter)
    else:  # openai / openrouter / any OpenAI-compatible gateway
        raw = _embed_openai(texts, api_key, model_name, batch_size, base_url=base_url, meter=meter)

    return _pad_to_target(raw)


def _embed_openai(
    texts: list[str], api_key: str, model_name: str, batch_size: int, base_url: str | None = None,
    meter: dict | None = None,
) -> list[list[float]]:
    """Embed using OpenAI API or an OpenAI-compatible gateway (OpenRouter…)."""
    client = openai.OpenAI(api_key=api_key, base_url=base_url or None, timeout=120)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(input=batch, model=model_name)
        if meter is not None:
            meter["calls"] += 1
            if getattr(response, "usage", None) and response.usage.prompt_tokens is not None:
                meter["tokens"] = meter.get("tokens", 0) + response.usage.prompt_tokens
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


def _embed_google(
    texts: list[str], api_key: str, model_name: str, batch_size: int, meter: dict | None = None
) -> list[list[float]]:
    """Embed using Google Gemini API."""
    from google import genai

    client = genai.Client(api_key=api_key)
    all_embeddings: list[list[float]] = []

    # Google API needs full model path
    if not model_name.startswith("models/"):
        model_name = f"models/{model_name}"

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        result = client.models.embed_content(
            model=model_name,
            contents=batch,
        )
        if meter is not None:
            meter["calls"] += 1  # the embed API reports no token counts → estimated by the caller
        all_embeddings.extend([e.values for e in result.embeddings])

    return all_embeddings

