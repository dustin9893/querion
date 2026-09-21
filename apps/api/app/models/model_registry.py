"""Predefined AI model registry — provider + purpose + dimensions."""

MODELS = [
    # --- OpenAI Embeddings ---
    {"provider": "openai", "model": "text-embedding-3-small", "purpose": "embedding", "dimensions": 1536, "label": "Text Embedding 3 Small"},
    {"provider": "openai", "model": "text-embedding-ada-002", "purpose": "embedding", "dimensions": 1536, "label": "Ada 002 (Legacy)"},
    # --- OpenAI LLMs ---
    {"provider": "openai", "model": "gpt-4o", "purpose": "llm", "dimensions": None, "label": "GPT-4o"},
    {"provider": "openai", "model": "gpt-4o-mini", "purpose": "llm", "dimensions": None, "label": "GPT-4o Mini"},
    {"provider": "openai", "model": "gpt-4-turbo", "purpose": "llm", "dimensions": None, "label": "GPT-4 Turbo"},
    {"provider": "openai", "model": "gpt-3.5-turbo", "purpose": "llm", "dimensions": None, "label": "GPT-3.5 Turbo"},
    # --- Google Embeddings ---
    {"provider": "google", "model": "gemini-embedding-001", "purpose": "embedding", "dimensions": 768, "label": "Gemini Embedding 001"},
    {"provider": "google", "model": "gemini-embedding-2-preview", "purpose": "embedding", "dimensions": 768, "label": "Gemini Embedding 2 Preview"},
    # --- Google LLMs ---
    {"provider": "google", "model": "gemini-2.5-flash", "purpose": "llm", "dimensions": None, "label": "Gemini 2.5 Flash"},
    {"provider": "google", "model": "gemini-2.5-pro", "purpose": "llm", "dimensions": None, "label": "Gemini 2.5 Pro"},
    {"provider": "google", "model": "gemini-2.0-flash-lite", "purpose": "llm", "dimensions": None, "label": "Gemini 2.0 Flash Lite"},
    # --- OpenRouter (OpenAI-compatible gateway, https://openrouter.ai/api/v1) ---
    {"provider": "openrouter", "model": "openai/text-embedding-3-small", "purpose": "embedding", "dimensions": 1536, "label": "OpenAI Text Embedding 3 Small (via OpenRouter)"},
    {"provider": "openrouter", "model": "qwen/qwen3-embedding-8b", "purpose": "embedding", "dimensions": 4096, "label": "Qwen3 Embedding 8B (4096d, sẽ bị cắt về 1536)"},
    {"provider": "openrouter", "model": "google/gemini-embedding-001", "purpose": "embedding", "dimensions": 3072, "label": "Gemini Embedding 001 (3072d, sẽ bị cắt về 1536)"},
    {"provider": "openrouter", "model": "openai/gpt-4o-mini", "purpose": "llm", "dimensions": None, "label": "GPT-4o Mini (via OpenRouter)"},
    {"provider": "openrouter", "model": "google/gemini-2.5-flash", "purpose": "llm", "dimensions": None, "label": "Gemini 2.5 Flash (via OpenRouter)"},
    {"provider": "openrouter", "model": "anthropic/claude-sonnet-4", "purpose": "llm", "dimensions": None, "label": "Claude Sonnet 4 (via OpenRouter)"},
    {"provider": "openrouter", "model": "qwen/qwen3-235b-a22b", "purpose": "llm", "dimensions": None, "label": "Qwen3 235B (via OpenRouter)"},
    # --- GreenNode MaaS (VNG Cloud AI Platform) — endpoint của hackathon, OpenAI-compatible ---
    {"provider": "vngcloud", "model": "google/gemma-4-31b-it", "purpose": "llm", "dimensions": None, "label": "Gemma 4 31B IT (GreenNode MaaS, nhanh)"},
    {"provider": "vngcloud", "model": "qwen/qwen3.6-flash", "purpose": "llm", "dimensions": None, "label": "Qwen 3.6 Flash (GreenNode MaaS)"},
    {"provider": "vngcloud", "model": "z-ai/glm-5.2-hackathon", "purpose": "llm", "dimensions": None, "label": "GLM 5.2 Hackathon (GreenNode MaaS, reasoning, chậm)"},
    # --- Anthropic LLMs ---
    {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "purpose": "llm", "dimensions": None, "label": "Claude Sonnet 4"},
    {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022", "purpose": "llm", "dimensions": None, "label": "Claude 3.5 Sonnet"},
    {"provider": "anthropic", "model": "claude-3-5-haiku-20241022", "purpose": "llm", "dimensions": None, "label": "Claude 3.5 Haiku"},
]

PROVIDERS = [
    {"value": "openai", "label": "OpenAI", "base_url": None},
    {"value": "google", "label": "Google Gemini", "base_url": None},
    {"value": "anthropic", "label": "Anthropic", "base_url": None},
    {"value": "openrouter", "label": "OpenRouter (OpenAI-compatible)", "base_url": "https://openrouter.ai/api/v1"},
    {"value": "vngcloud", "label": "GreenNode MaaS — VNG Cloud (OpenAI-compatible)", "base_url": "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"},
    {"value": "openai_compatible", "label": "OpenAI-compatible khác (tự nhập base URL)", "base_url": ""},
]

# Anything that is not google/anthropic speaks the OpenAI wire protocol.
OPENAI_COMPATIBLE = {"openai", "openrouter", "vngcloud", "openai_compatible"}


def default_base_url(provider: str) -> str | None:
    for p in PROVIDERS:
        if p["value"] == provider:
            return p.get("base_url") or None
    return None


def get_models_for_provider(provider: str, purpose: str | None = None) -> list[dict]:
    """Get models for a provider, optionally filtered by purpose."""
    result = [m for m in MODELS if m["provider"] == provider]
    if purpose:
        result = [m for m in result if m["purpose"] == purpose]
    return result


def get_model_dimensions(provider: str, model: str) -> int | None:
    """Get embedding dimensions for a specific model."""
    for m in MODELS:
        if m["provider"] == provider and m["model"] == model:
            return m["dimensions"]
    return None
