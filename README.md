# Flickr MCP

> English ｜ [繁體中文](README.zh.md)

Give Claude direct access to your Flickr — browse your photostream, pull direct
image URLs for embedding, upload, and manage albums. A thin [Model Context
Protocol](https://modelcontextprotocol.io) wrapper around Flickr's official API
(OAuth 1.0a signed, read + write).

Status: 🟢 all 10 tools live-verified (6 read + 4 write) against a real
~1500-photo account. The first live upload test surfaced two real bugs in
`upload_photo` — an OAuth multipart-signing failure (401) and a non-ASCII
title signing crash — both now fixed (HMAC-SHA1 signed by hand, UTF-8 safe).

## Tools

**Read**
- `whoami` — verify auth succeeded (returns the logged-in user id / name)
- `list_albums` — list your albums (photosets)
- `list_album_photos` — list photos in an album (each with a ready-to-use 1024px URL)
- `search_photos` — search (defaults to your own photos only)
- `get_photo_info` — full metadata for one photo (title / description / tags / taken date / visibility / page URL)
- `get_photo_sizes` — every available size with its direct source URL (**the reliable source for embed URLs**)

**Write**
- `upload_photo` — upload a local image (**private by default**, nothing goes public by accident)
- `create_album` — create an album (Flickr requires an existing photo as the cover)
- `add_photo_to_album` — add a photo to an album
- `set_photo_meta` — update a photo's title / description

## Install

```bash
git clone https://github.com/vulture-s/flickr-mcp.git
cd flickr-mcp
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Get credentials (four strings)

1. Create an app at <https://www.flickr.com/services/apps/create/> (non-commercial
   is fine) and copy its **Key** and **Secret**.
2. Exchange them for an access token:
   ```bash
   export FLICKR_API_KEY=your_key
   export FLICKR_API_SECRET=your_secret
   python authorize.py
   ```
   Open the printed URL → approve → paste the 9-digit code Flickr shows back into
   the terminal. The script prints the four `FLICKR_*` variables.

> Requests `write` permission (covers read + upload + album management). The
> script never writes to disk — you paste the tokens into your config yourself.

### Add to Claude Code

Use `claude mcp add`, or add to your MCP config JSON:

```json
{
  "mcpServers": {
    "flickr": {
      "command": "python",
      "args": ["-m", "flickr_mcp.server"],
      "cwd": "/absolute/path/to/flickr-mcp",
      "env": {
        "FLICKR_API_KEY": "...",
        "FLICKR_API_SECRET": "...",
        "FLICKR_OAUTH_TOKEN": "...",
        "FLICKR_OAUTH_TOKEN_SECRET": "..."
      }
    }
  }
}
```

Once it's connected, ask Claude to run `whoami` to confirm auth works.

## Typical embedding workflow

1. `list_albums` → find the album_id you want
2. `list_album_photos` or `get_photo_sizes` → get each photo's direct URL
3. Drop the URLs into your own HTML/CSS (images live on Flickr, you control the look)

## Notes

- **Upload defaults to private**: `upload_photo`'s `is_public` defaults to False;
  you must explicitly set it to go public.
- **Credentials never touch git**: `.env` is gitignored; only `.env.example` is
  tracked. Prefer passing the four vars via your MCP config's `env` block.
- **`write` perms exclude deletion**: Flickr's `write` scope covers upload and
  album management but *not* deleting photos — a test upload can only be removed
  from the Flickr website. Think before you upload.
- The OAuth token is long-lived; you won't need to re-run `authorize.py` unless
  you revoke it in Flickr's account settings.

## License

MIT — see [LICENSE](LICENSE).
