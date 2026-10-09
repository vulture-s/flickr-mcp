# Known bug classes

Bugs found in this repo, grouped by the mistake rather than the function. Each
class has a test that enumerates **every** tool / HTTP call, so a new tool that
repeats the mistake fails CI (`python -m pytest -q tests`, run by
`.github/workflows/ci.yml` on 3.10–3.13).

| Class | First instance (fixed in) | Single-case regression | Class-level test (`tests/test_tool_contracts.py`) |
|---|---|---|---|
| An omitted optional field is sent as `""` and overwrites what Flickr stores (Flickr keeps no history) | `set_photo_meta` title-only wiped the description (#1) | `tests/test_set_photo_meta.py` | `test_omitted_optional_fields_are_never_sent_as_empty[<every tool>]`, `test_client_drops_none_params` |
| Outbound HTTP call without a timeout → the MCP tool hangs forever | REST calls and upload (#1) | `tests/test_client_timeout.py` | `test_every_http_call_has_a_timeout_ratchet` (AST scan of `flickr_mcp/` + `authorize.py`) |
| A failed write reported as success | — (guard against regression) | — | `test_every_tool_reports_failure_as_error[<every tool>]` |

Rules of thumb:

- Flickr `set*` methods replace the whole field set. Read back anything the
  caller did not pass, and send `None` (dropped by `FlickrClient.call`) rather
  than `""` for "not given".
- Every `requests` / `OAuth1Session` call takes `timeout=`.
- Every tool catches `FlickrError` and returns `{"error": ...}`.

Ratchet: `TIMEOUT_BASELINE` lists the two token fetches in `authorize.py` that
still have no timeout. It may only shrink — the test fails if one is fixed but
left in the list.

Note: `hevin-ai-os/apps/toolbox/flickr-mcp` carries a copy of `server.py`;
fixes here need to be mirrored there.
