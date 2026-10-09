"""Structural tests: every tool / every HTTP call, not one function.

The bugs fixed in #1 were instances of three classes; these tests enumerate
all members of each class so the next tool or the next HTTP call that repeats
the mistake fails here (see docs/known-bug-classes.md):

1. an omitted optional field is sent to Flickr as "" and wipes the stored
   value (set_photo_meta wiped descriptions);
2. an outbound HTTP call without a timeout hangs the MCP tool forever;
3. a write that failed is reported as done (every tool must turn a
   FlickrError into {"error": ...}, never into {"updated": True}).

No network: the Flickr client is replaced by recorders.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flickr_mcp import server  # noqa: E402
from flickr_mcp.client import FlickrError  # noqa: E402


def _tool_names():
    tree = ast.parse((ROOT / "flickr_mcp" / "server.py").read_text(encoding="utf-8"))
    names = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                src = ast.unparse(dec)
                if src.startswith("mcp.tool"):
                    names.append(node.name)
    return names


TOOLS = _tool_names()


def test_tool_enumeration_is_not_empty():
    # Guard the guard: if decorator detection breaks, every parametrized test
    # below would silently run zero times.
    assert len(TOOLS) >= 12, TOOLS
    assert "set_photo_meta" in TOOLS and "upload_photo" in TOOLS


def _fn(name):
    obj = getattr(server, name)
    return getattr(obj, "fn", obj)


def _required_args(fn, tmp_path):
    args = {}
    for p in inspect.signature(fn).parameters.values():
        if p.default is not inspect.Parameter.empty:
            continue
        if p.name == "photo_path":
            f = tmp_path / "x.jpg"
            f.write_bytes(b"\xff\xd8\xff")
            args[p.name] = str(f)
        else:
            args[p.name] = "123"
    return args


class Recorder:
    """Records every call; getInfo returns populated fields for read-back."""

    def __init__(self):
        self.calls = []

    def call(self, method, http="GET", **params):
        self.calls.append((method, http.upper(), params))
        if method == "flickr.photos.getInfo":
            return {"stat": "ok", "photo": {
                "title": {"_content": "kept title"},
                "description": {"_content": "kept description"},
            }}
        return {"stat": "ok"}

    def upload(self, photo_path, **kw):
        self.calls.append(("upload", "POST", kw))
        return "999"


class Failing:
    def call(self, method, http="GET", **params):
        raise FlickrError(f"{method} failed: boom (code 99)")

    def upload(self, photo_path, **kw):
        raise FlickrError("upload failed: boom")


# --- Class 1: omitted optional field must not be written as "" ------------

@pytest.mark.parametrize("name", TOOLS)
def test_omitted_optional_fields_are_never_sent_as_empty(name, monkeypatch, tmp_path):
    fn = _fn(name)
    rec = Recorder()
    monkeypatch.setattr(server, "_client", lambda: rec)
    args = _required_args(fn, tmp_path)
    # Tools whose every field is optional (set_photo_meta) need *one* field to
    # do anything; pass one and check the others.
    optional_str = [p.name for p in inspect.signature(fn).parameters.values()
                    if p.default is None]
    if name == "set_photo_meta":
        args["title"] = "new title"
    fn(**args)
    passed = set(args)
    for method, http, params in rec.calls:
        if http != "POST":
            continue
        for key, val in params.items():
            if key in passed or key not in optional_str:
                continue
            # None is dropped by FlickrClient.call / upload (pinned below);
            # "" is sent and overwrites.
            assert val != "", (
                f"{name} sent omitted field {key!r}={val!r} to {method}; "
                "that overwrites the stored value on Flickr")


def test_client_drops_none_params(monkeypatch):
    """Class 1 relies on this: an omitted (None) field never reaches Flickr."""
    from flickr_mcp import client as client_mod

    sent = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"stat": "ok"}

    class Sess:
        def post(self, url, data=None, **kw):
            sent.append(data)
            return Resp()

    c = client_mod.FlickrClient("k", "s", "t", "ts")
    monkeypatch.setattr(c, "_session", lambda: Sess())
    c.call("flickr.photosets.create", http="POST", title="t", description=None)
    assert "description" not in sent[0]


def test_set_photo_meta_resends_both_stored_fields():
    # The concrete instance behind class 1, kept explicit.
    rec = Recorder()
    server._client, orig = (lambda: rec), server._client
    try:
        _fn("set_photo_meta")("1", description="new")
    finally:
        server._client = orig
    (params,) = [p for m, _, p in rec.calls if m == "flickr.photos.setMeta"]
    assert params["title"] == "kept title"


# --- Class 3: failures must surface as errors ------------------------------

@pytest.mark.parametrize("name", TOOLS)
def test_every_tool_reports_failure_as_error(name, monkeypatch, tmp_path):
    fn = _fn(name)
    monkeypatch.setattr(server, "_client", lambda: Failing())
    args = _required_args(fn, tmp_path)
    if name == "set_photo_meta":
        args["title"] = "t"
    out = fn(**args)
    assert isinstance(out, dict) and "error" in out, (name, out)
    success_flags = {k: v for k, v in out.items()
                     if k in ("updated", "added", "deleted") and v}
    assert not success_flags, (name, out)


# --- Class 2: every outbound HTTP call carries a timeout -------------------

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "request",
                "fetch_request_token", "fetch_access_token"}
HTTP_RECEIVERS = {"requests", "session", "oauth", "httpx", "client_http"}

# Ratchet: known calls without a timeout. May only shrink. authorize.py is the
# one-off interactive OAuth helper; its two token fetches still have none.
TIMEOUT_BASELINE = {
    ("authorize.py", "oauth.fetch_request_token"),
    ("authorize.py", "oauth.fetch_access_token"),
}


def _http_calls_without_timeout():
    files = sorted((ROOT / "flickr_mcp").glob("*.py")) + [ROOT / "authorize.py"]
    found, total = set(), 0
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            recv = node.func.value
            if not (isinstance(recv, ast.Name) and recv.id in HTTP_RECEIVERS
                    and node.func.attr in HTTP_METHODS):
                continue
            total += 1
            if not any(k.arg == "timeout" for k in node.keywords):
                found.add((path.name, f"{recv.id}.{node.func.attr}"))
    return found, total


def test_every_http_call_has_a_timeout_ratchet():
    found, total = _http_calls_without_timeout()
    assert total >= 5, f"scanner found only {total} HTTP calls — detection broke?"
    new = found - TIMEOUT_BASELINE
    assert not new, f"HTTP call(s) without timeout=: {sorted(new)}"
    fixed = TIMEOUT_BASELINE - found
    assert not fixed, f"fixed — remove from TIMEOUT_BASELINE: {sorted(fixed)}"
