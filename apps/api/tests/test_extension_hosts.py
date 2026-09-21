"""The browser extension opens an assistant by default on pages whose host matches one of the
assistant's `extension_hosts`. Admins type those patterns by hand, so validation must be strict
about shape and the matcher must be predictable.

Run: cd apps/api && pytest tests/test_extension_hosts.py -v
"""

import pytest
from fastapi import HTTPException

from app.services.extension import host_matches, normalize_host, validate_hosts


@pytest.mark.parametrize("raw, expected", [
    ("bpm.msb.local", "bpm.msb.local"),
    ("  BPM.MSB.LOCAL/ ", "bpm.msb.local"),
    ("https://bpm.msb.local", "bpm.msb.local"),      # a pasted URL loses its scheme
    ("*.msb.local", "*.msb.local"),
    ("localhost:8092", "localhost:8092"),
])
def test_hosts_are_normalised(raw, expected):
    assert normalize_host(raw) == expected


@pytest.mark.parametrize("raw", [
    "", "bpm.msb.local/app", "bpm.msb.local?x=1", "user@bpm.msb.local", "bpm.*.local", "*msb.local",
    "-bad.local", "a b.local", "http://", "bpm.msb.local:99999x",
])
def test_bad_hosts_are_refused(raw):
    with pytest.raises(HTTPException) as err:
        normalize_host(raw)
    assert err.value.status_code == 400


def test_validate_dedupes_and_caps():
    assert validate_hosts(["a.local", "A.LOCAL", "b.local"]) == ["a.local", "b.local"]
    with pytest.raises(HTTPException):
        validate_hosts([f"h{i}.local" for i in range(21)])
    with pytest.raises(HTTPException):
        validate_hosts("a.local")  # type: ignore[arg-type]


@pytest.mark.parametrize("pattern, host, expected", [
    ("bpm.msb.local", "bpm.msb.local", True),
    ("bpm.msb.local", "BPM.msb.local", True),
    ("bpm.msb.local", "bpm.msb.local:8443", True),       # no port in the rule → any port
    ("localhost:8092", "localhost:8092", True),
    ("localhost:8092", "localhost:8090", False),         # port in the rule → exact
    ("localhost:8092", "localhost", False),
    ("*.msb.local", "bpm.msb.local", True),
    ("*.msb.local", "a.b.msb.local", True),
    ("*.msb.local", "msb.local", False),                 # the wildcard needs at least one label
    ("*.msb.local", "evilmsb.local", False),
    ("bpm.msb.local", "bpm.msb.local.evil.com", False),
    ("", "bpm.msb.local", False),
])
def test_host_matching(pattern, host, expected):
    assert host_matches(pattern, host) is expected
