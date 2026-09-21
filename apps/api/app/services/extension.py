"""Browser extension surface: which assistants the floating bubble may show, and on which pages.

The extension is a fourth channel next to the staff portal, the embedded widget and the customer
page. Two things live here and nowhere else:

* validation of `apps.extension_hosts` — intranet host patterns an admin types on the assistant;
* `host_matches` — the rule the bubble uses to pick the default assistant for the page it is on.

The flag and the hosts are product / audit controls, not a security boundary against the staff
member: they already hold a staff token. The boundary that matters is enforced elsewhere
(`_staff_can_use`: unit scoping, publication, audience).
"""

from __future__ import annotations

import re

from fastapi import HTTPException

CLIENTS = ("portal", "extension")   # value of the `client` claim in a staff JWT
MAX_HOSTS = 20
# host or *.host, optional :port — no scheme, no path, no wildcard except a leading "*."
_HOST_RE = re.compile(r"^(\*\.)?[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?)*(:\d{1,5})?$")


def normalize_host(raw: str) -> str:
    value = (raw or "").strip().lower().rstrip("/")
    if "://" in value:
        value = value.split("://", 1)[1]
    if not value:
        raise HTTPException(status_code=400, detail="Tên miền trống")
    if "/" in value or "?" in value or "#" in value or "@" in value:
        raise HTTPException(status_code=400, detail=f"Tên miền không được chứa đường dẫn hay thông tin đăng nhập: '{raw}'")
    if not _HOST_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"Tên miền không hợp lệ: '{raw}'. Dạng đúng: bpm.msb.local, *.msb.local hoặc localhost:8092",
        )
    return value


def validate_hosts(hosts: list[str]) -> list[str]:
    if not isinstance(hosts, list):
        raise HTTPException(status_code=400, detail="extension_hosts phải là danh sách")
    if len(hosts) > MAX_HOSTS:
        raise HTTPException(status_code=400, detail=f"Tối đa {MAX_HOSTS} tên miền")
    out: list[str] = []
    for raw in hosts:
        host = normalize_host(str(raw))
        if host not in out:
            out.append(host)
    return out


def host_matches(pattern: str, host: str) -> bool:
    """`*.msb.local` matches `bpm.msb.local` and `a.b.msb.local`, not `msb.local`; exact otherwise.
    A pattern without a port matches any port; with a port it must match exactly."""
    pattern, host = (pattern or "").lower(), (host or "").lower()
    if not pattern or not host:
        return False
    p_host, _, p_port = pattern.partition(":")
    h_host, _, h_port = host.partition(":")
    if p_port and p_port != h_port:
        return False
    if p_host.startswith("*."):
        return h_host.endswith(p_host[1:]) and h_host != p_host[2:]
    return p_host == h_host
