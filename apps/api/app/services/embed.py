"""Embeddable widget helpers: origin allowlist + widget config validation.

An *origin* is ``scheme://host[:port]`` exactly as the browser reports it in
``window.location.origin`` — no path, no query, no trailing slash, no wildcard.
The same list feeds the CSP ``frame-ancestors`` header of the /embed page, the
in-iframe parent-origin check, and the ``X-Embed-Origin`` audit attribution.
"""

import re
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException

MAX_ORIGINS = 20
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

DEFAULT_WIDGET: dict[str, Any] = {
    "title": None,                 # falls back to the assistant name
    "subtitle": "Trả lời từ tài liệu chính thức",
    "greeting": "Xin chào! Tôi có thể giúp gì cho bạn?",
    "primary_color": "#ee6d1f",
    "position": "right",           # right | left
    "launcher_text": "Hỗ trợ trực tuyến",
    "suggestions": [],
    "show_powered_by": True,
    "theme": "light",              # light | dark | auto
    "disclaimer": None,            # falls back to the audience default
}

_LIMITS = {"title": 80, "subtitle": 80, "greeting": 300, "launcher_text": 40, "disclaimer": 300}


def normalize_origin(raw: str) -> str:
    """Validate + canonicalise one origin; raises HTTPException(400) on bad input."""
    value = (raw or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail=f"Origin không hợp lệ: '{raw}'. Dạng đúng: https://ten-mien.vn hoặc http://localhost:8090")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail=f"Origin không được chứa đường dẫn, query hay thông tin đăng nhập: '{raw}'")
    if "*" in parsed.netloc:
        raise HTTPException(status_code=400, detail="Chưa hỗ trợ wildcard; nhập từng origin cụ thể")
    host = parsed.hostname.lower()
    default_port = 443 if parsed.scheme == "https" else 80
    port = f":{parsed.port}" if parsed.port and parsed.port != default_port else ""
    return f"{parsed.scheme}://{host}{port}"


def validate_origins(origins: list[str]) -> list[str]:
    if not isinstance(origins, list):
        raise HTTPException(status_code=400, detail="allowed_origins phải là danh sách")
    if len(origins) > MAX_ORIGINS:
        raise HTTPException(status_code=400, detail=f"Tối đa {MAX_ORIGINS} origin")
    out: list[str] = []
    for o in origins:
        n = normalize_origin(str(o))
        if n not in out:
            out.append(n)
    return out


def validate_widget_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Whitelist keys and bound every value; unknown keys are dropped."""
    if not isinstance(cfg, dict):
        raise HTTPException(status_code=400, detail="widget_config phải là object")
    out: dict[str, Any] = {}
    for key, max_len in _LIMITS.items():
        if key in cfg and cfg[key] is not None:
            val = str(cfg[key]).strip()
            if len(val) > max_len:
                raise HTTPException(status_code=400, detail=f"widget_config.{key} tối đa {max_len} ký tự")
            out[key] = val or None
    if "primary_color" in cfg and cfg["primary_color"]:
        color = str(cfg["primary_color"]).strip()
        if not _HEX_COLOR.match(color):
            raise HTTPException(status_code=400, detail="primary_color phải là mã hex dạng #rrggbb")
        out["primary_color"] = color.lower()
    if "position" in cfg and cfg["position"]:
        if cfg["position"] not in ("right", "left"):
            raise HTTPException(status_code=400, detail="position phải là 'right' hoặc 'left'")
        out["position"] = cfg["position"]
    if "theme" in cfg and cfg["theme"]:
        if cfg["theme"] not in ("light", "dark", "auto"):
            raise HTTPException(status_code=400, detail="theme phải là light | dark | auto")
        out["theme"] = cfg["theme"]
    if "show_powered_by" in cfg:
        out["show_powered_by"] = bool(cfg["show_powered_by"])
    if "suggestions" in cfg and cfg["suggestions"] is not None:
        sugg = cfg["suggestions"]
        if not isinstance(sugg, list) or len(sugg) > 4:
            raise HTTPException(status_code=400, detail="suggestions tối đa 4 mục")
        cleaned = [str(s).strip()[:120] for s in sugg if str(s).strip()]
        out["suggestions"] = cleaned
    return out


def effective_widget(app_name: str, cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Merge stored config over defaults; fill title from the assistant name."""
    merged = {**DEFAULT_WIDGET, **{k: v for k, v in (cfg or {}).items() if v is not None}}
    if not merged.get("title"):
        merged["title"] = app_name
    return merged
