"""REST calls must carry a timeout (audit 2026-10-09): without one, a
half-open connection hangs the MCP tool forever with no error. No network."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flickr_mcp import client as client_mod  # noqa: E402


class FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"stat": "ok"}


class FakeSession:
    def __init__(self):
        self.kwargs = []

    def get(self, url, **kw):
        self.kwargs.append(kw)
        return FakeResp()

    def post(self, url, **kw):
        self.kwargs.append(kw)
        return FakeResp()


@pytest.mark.parametrize("http", ["GET", "POST"])
def test_rest_call_has_timeout(monkeypatch, http):
    c = client_mod.FlickrClient("k", "s", "t", "ts")
    sess = FakeSession()
    monkeypatch.setattr(c, "_session", lambda: sess)
    c.call("flickr.test.login", http=http)
    assert sess.kwargs[0].get("timeout") == client_mod.REST_TIMEOUT
    connect, read = client_mod.REST_TIMEOUT
    assert 0 < connect <= 30 and 0 < read <= 120
