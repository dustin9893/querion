"""Assistant logo (avatar): validation, normalisation, storage and public URL.

Accepted uploads: PNG, JPEG, WebP, GIF, BMP, ICO (raster) and SVG, ≤ 1 MB.

- Rasters are decoded with Pillow — which proves the bytes really are an image — then
  re-encoded as PNG at most 512×512. That strips EXIF/metadata and any odd container
  feature before the file is ever served to a browser.
- SVG is kept as-is only if it carries no script, event handler, DOCTYPE/ENTITY or
  external reference; the public endpoint additionally serves it with a sandboxing CSP,
  so an SVG opened directly in a tab can never run code on the API origin.

The image is stored in MinIO next to the assistant's other data and served without a key
by GET /v1/public/assistants/{id}/logo (a logo is shown on public websites anyway).
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone

from fastapi import HTTPException

from app.models.app import App
from app.storage import delete_file, upload_file

MAX_LOGO_BYTES = 1 * 1024 * 1024
MAX_SIDE = 512                      # rasters are downscaled (never upscaled) to fit
MAX_PIXELS = 25_000_000             # refuse absurd dimensions before decoding fully
RASTER_FORMATS = {"PNG", "JPEG", "WEBP", "GIF", "BMP", "ICO"}
ACCEPTED_LABEL = "PNG, JPG, WebP, GIF, ICO hoặc SVG"

# Anything that could execute or fetch from an SVG: script/foreignObject/embeds, event
# handlers, javascript: URLs, HTML data URLs, and href/url() pointing outside the file.
_SVG_FORBIDDEN = re.compile(
    r"<\s*(?:script|foreignObject|iframe|embed|object|handler|listener)\b"
    r"|\son[a-z]+\s*="
    r"|javascript:"
    r"|data:text/html"
    r"|(?:xlink:)?href\s*=\s*[\"'](?!#|data:image/)"
    r"|url\(\s*[\"']?(?!#|data:image/)",
    re.I,
)
_SVG_DOCTYPE = re.compile(r"<!DOCTYPE|<!ENTITY", re.I)


def _bad(msg: str) -> HTTPException:
    return HTTPException(status_code=400, detail=msg)


def _check_svg(data: bytes) -> bytes:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _bad("SVG phải được mã hoá UTF-8")
    if _SVG_DOCTYPE.search(text):
        raise _bad("SVG không được chứa DOCTYPE/ENTITY")
    if _SVG_FORBIDDEN.search(text):
        raise _bad("SVG chứa script, sự kiện hoặc tham chiếu ra ngoài — không được phép")
    try:
        import defusedxml.ElementTree as ET  # refuses DTD / entity tricks outright
    except ImportError:  # pragma: no cover — DOCTYPE/ENTITY were already rejected above
        import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise _bad("Tệp SVG không hợp lệ")
    if not root.tag.lower().endswith("svg"):
        raise _bad("Tệp không phải SVG")
    return data


def _normalise_raster(data: bytes) -> bytes:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = (probe.format or "").upper()
            if fmt not in RASTER_FORMATS:
                raise _bad(f"Định dạng {fmt or 'không rõ'} không được hỗ trợ ({ACCEPTED_LABEL})")
            if probe.width * probe.height > MAX_PIXELS:
                raise _bad("Ảnh quá lớn (tối đa 5000×5000 điểm ảnh)")
            probe.verify()  # structural check; the image object is unusable afterwards
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            im = im.convert("RGBA")             # keep transparency; palette/CMYK → RGBA
            im.thumbnail((MAX_SIDE, MAX_SIDE))  # aspect-preserving, never upscales
            out = io.BytesIO()
            im.save(out, format="PNG", optimize=True)
            return out.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise _bad(f"Tệp không phải ảnh hợp lệ ({ACCEPTED_LABEL})")


def normalise_logo(data: bytes) -> tuple[bytes, str, str]:
    """Validate an upload and return (bytes to store, content type, file extension)."""
    if not data:
        raise _bad("Tệp rỗng")
    if len(data) > MAX_LOGO_BYTES:
        raise _bad("Logo tối đa 1 MB")
    head = data[:4096].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(b"<") and b"<svg" in head.lower():
        return _check_svg(data), "image/svg+xml", "svg"
    return _normalise_raster(data), "image/png", "png"


def storage_key_for(app: App, ext: str) -> str:
    return f"workspaces/{app.workspace_id}/apps/{app.id}/logo.{ext}"


def logo_url(app: App) -> str | None:
    """API-relative URL of the logo (the web prefixes its API base); None when there is no logo.
    ?v= changes on every upload so browsers and the widget never show a stale image."""
    if not app.logo_key:
        return None
    version = int(app.logo_updated_at.timestamp()) if app.logo_updated_at else 0
    return f"/v1/public/assistants/{app.id}/logo?v={version}"


def store_logo(app: App, raw: bytes) -> None:
    """Validate + normalise + upload; updates the app row (caller commits)."""
    data, content_type, ext = normalise_logo(raw)
    key = storage_key_for(app, ext)
    if app.logo_key and app.logo_key != key:
        try:
            delete_file(app.logo_key)
        except Exception:
            pass
    upload_file(key, data, content_type)
    app.logo_key = key
    app.logo_content_type = content_type
    app.logo_updated_at = datetime.now(timezone.utc)


def remove_logo(app: App) -> None:
    """Delete the stored image (best effort) and clear the columns (caller commits)."""
    if app.logo_key:
        try:
            delete_file(app.logo_key)
        except Exception:
            pass
    app.logo_key = None
    app.logo_content_type = None
    app.logo_updated_at = None
