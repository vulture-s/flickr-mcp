"""set_photo_meta must not wipe fields the caller did not pass (audit
2026-10-09). No network: the Flickr client is replaced by a recorder."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flickr_mcp import client as client_mod  # noqa: E402
from flickr_mcp import server  # noqa: E402


class RecordingClient:
    def __init__(self, title="old title", description="old description"):
        self.calls = []
        self._title = title
        self._description = description

    def call(self, method, http="GET", **params):
        self.calls.append((method, http, params))
        if method == "flickr.photos.getInfo":
            return {
                "stat": "ok",
                "photo": {
                    "title": {"_content": self._title},
                    "description": {"_content": self._description},
                },
            }
        return {"stat": "ok"}

    def set_meta_params(self):
        sent = [p for m, _, p in self.calls if m == "flickr.photos.setMeta"]
        assert len(sent) == 1
        return sent[0]


@pytest.fixture
def rec(monkeypatch):
    r = RecordingClient()
    monkeypatch.setattr(server, "_client", lambda: r)
    return r


def _tool(fn):
    # FastMCP's decorator may wrap; fall back to the raw function if so.
    return getattr(fn, "fn", fn)


def test_title_only_keeps_existing_description(rec):
    out = _tool(server.set_photo_meta)("123", title="new title")
    sent = rec.set_meta_params()
    assert sent["title"] == "new title"
    assert sent["description"] == "old description"
    assert out.get("updated") is True


def test_description_only_keeps_existing_title(rec):
    _tool(server.set_photo_meta)("123", description="new desc")
    sent = rec.set_meta_params()
    assert sent == {"photo_id": "123", "title": "old title", "description": "new desc"}


def test_both_given_skips_getinfo(rec):
    _tool(server.set_photo_meta)("123", title="t", description="d")
    assert [m for m, _, _ in rec.calls] == ["flickr.photos.setMeta"]
    assert rec.set_meta_params()["description"] == "d"


def test_explicit_empty_description_still_clears(rec):
    # Clearing must stay possible — but only when asked for explicitly.
    _tool(server.set_photo_meta)("123", title="t", description="")
    assert rec.set_meta_params()["description"] == ""


def test_nothing_to_update_sends_nothing(rec):
    out = _tool(server.set_photo_meta)("123")
    assert "error" in out
    assert rec.calls == []


def test_getinfo_failure_does_not_write(monkeypatch):
    class Failing(RecordingClient):
        def call(self, method, http="GET", **params):
            self.calls.append((method, http, params))
            if method == "flickr.photos.getInfo":
                raise client_mod.FlickrError("boom")
            return {"stat": "ok"}

    r = Failing()
    monkeypatch.setattr(server, "_client", lambda: r)
    out = _tool(server.set_photo_meta)("123", title="t")
    assert "error" in out
    assert [m for m, _, _ in r.calls] == ["flickr.photos.getInfo"]
