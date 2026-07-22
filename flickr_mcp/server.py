"""Flickr MCP server (FastMCP).

Exposes read + write Flickr operations as MCP tools so Claude can browse your
photostream, pull direct image URLs for embedding, and manage albums/uploads.

Auth: needs the four FLICKR_* env vars (run authorize.py once to get the two
OAuth tokens). Every tool constructs a fresh client so a missing-credential
error surfaces as a clear tool result rather than a crash at startup.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from .client import FlickrClient, FlickrError

mcp = FastMCP("flickr")


def _client() -> FlickrClient:
    return FlickrClient()


def _photo_static_url(photo: Dict[str, Any], size: str = "b") -> str:
    """Build a live.staticflickr.com URL from a photo dict.

    size suffix: s/q/t/m/n/w/z/c/b/h/k (b = 1024px long edge, good for web).
    Used for quick embedding; use get_photo_sizes for the authoritative list.
    """
    server = photo.get("server")
    pid = photo.get("id")
    secret = photo.get("secret")
    return f"https://live.staticflickr.com/{server}/{pid}_{secret}_{size}.jpg"


# ----------------------------------------------------------------------------
# Read tools
# ----------------------------------------------------------------------------


@mcp.tool()
def whoami() -> Dict[str, Any]:
    """Verify credentials by calling flickr.test.login. Returns the logged-in
    user's id and username, or a clear error if auth is not set up."""
    try:
        data = _client().call("flickr.test.login")
    except FlickrError as exc:
        return {"error": str(exc)}
    user = data.get("user", {})
    return {
        "user_id": user.get("id"),
        "username": user.get("username", {}).get("_content"),
    }


@mcp.tool()
def list_albums(per_page: int = 100, page: int = 1) -> Dict[str, Any]:
    """List the authenticated user's albums (photosets): id, title, photo count,
    and primary photo id. Use list_album_photos to drill into one."""
    try:
        data = _client().call(
            "flickr.photosets.getList", per_page=per_page, page=page
        )
    except FlickrError as exc:
        return {"error": str(exc)}
    sets = data.get("photosets", {}).get("photoset", [])
    return {
        "total": data.get("photosets", {}).get("total"),
        "albums": [
            {
                "id": s.get("id"),
                "title": s.get("title", {}).get("_content"),
                "description": s.get("description", {}).get("_content"),
                "photos": s.get("photos"),
                "primary_photo_id": s.get("primary"),
            }
            for s in sets
        ],
    }


@mcp.tool()
def list_album_photos(
    album_id: str, per_page: int = 100, page: int = 1
) -> Dict[str, Any]:
    """List photos in an album. Each photo includes id, title, and a ready-to-use
    1024px static URL for embedding."""
    try:
        data = _client().call(
            "flickr.photosets.getPhotos",
            photoset_id=album_id,
            # No user_id: photosets.getPhotos rejects "me" ("User not found", code 2);
            # photoset_id already scopes to its owner for the authenticated session.
            per_page=per_page,
            page=page,
        )
    except FlickrError as exc:
        return {"error": str(exc)}
    photoset = data.get("photoset", {})
    photos = photoset.get("photo", [])
    return {
        "album_id": album_id,
        "pages": photoset.get("pages"),
        "total": photoset.get("total"),
        "photos": [
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "url": _photo_static_url(p),
            }
            for p in photos
        ],
    }


@mcp.tool()
def search_photos(
    text: Optional[str] = None,
    tags: Optional[str] = None,
    mine_only: bool = True,
    per_page: int = 50,
    page: int = 1,
) -> Dict[str, Any]:
    """Search photos. By default restricted to the authenticated user's own
    photos (mine_only). Provide text and/or comma-separated tags."""
    params: Dict[str, Any] = {
        "text": text,
        "tags": tags,
        "per_page": per_page,
        "page": page,
    }
    if mine_only:
        params["user_id"] = "me"
    try:
        data = _client().call("flickr.photos.search", **params)
    except FlickrError as exc:
        return {"error": str(exc)}
    block = data.get("photos", {})
    return {
        "pages": block.get("pages"),
        "total": block.get("total"),
        "photos": [
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "url": _photo_static_url(p),
            }
            for p in block.get("photo", [])
        ],
    }


@mcp.tool()
def get_photo_info(photo_id: str) -> Dict[str, Any]:
    """Full metadata for one photo: title, description, tags, dates, visibility,
    and the Flickr page URL."""
    try:
        data = _client().call("flickr.photos.getInfo", photo_id=photo_id)
    except FlickrError as exc:
        return {"error": str(exc)}
    p = data.get("photo", {})
    urls = p.get("urls", {}).get("url", [])
    page_url = urls[0].get("_content") if urls else None
    return {
        "id": p.get("id"),
        "title": p.get("title", {}).get("_content"),
        "description": p.get("description", {}).get("_content"),
        "tags": [t.get("_content") for t in p.get("tags", {}).get("tag", [])],
        "taken": p.get("dates", {}).get("taken"),
        "is_public": p.get("visibility", {}).get("ispublic"),
        "page_url": page_url,
    }


@mcp.tool()
def get_photo_sizes(photo_id: str) -> Dict[str, Any]:
    """Authoritative list of available sizes for a photo, each with its direct
    source URL and pixel dimensions. This is the reliable source for embed URLs."""
    try:
        data = _client().call("flickr.photos.getSizes", photo_id=photo_id)
    except FlickrError as exc:
        return {"error": str(exc)}
    sizes = data.get("sizes", {}).get("size", [])
    return {
        "photo_id": photo_id,
        "sizes": [
            {
                "label": s.get("label"),
                "width": s.get("width"),
                "height": s.get("height"),
                "source": s.get("source"),
            }
            for s in sizes
        ],
    }


# ----------------------------------------------------------------------------
# Write tools
# ----------------------------------------------------------------------------


@mcp.tool()
def upload_photo(
    photo_path: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[str] = None,
    is_public: bool = False,
) -> Dict[str, Any]:
    """Upload a local image file to Flickr. Defaults to PRIVATE so nothing goes
    public by accident. Returns the new photo id."""
    try:
        photo_id = _client().upload(
            photo_path,
            title=title,
            description=description,
            tags=tags,
            is_public=1 if is_public else 0,
        )
    except FlickrError as exc:
        return {"error": str(exc)}
    return {"photo_id": photo_id, "is_public": is_public}


@mcp.tool()
def create_album(
    title: str, primary_photo_id: str, description: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new album (photoset). Flickr requires an existing photo id to be
    the album cover (primary_photo_id). Returns the new album id."""
    try:
        data = _client().call(
            "flickr.photosets.create",
            http="POST",
            title=title,
            description=description,
            primary_photo_id=primary_photo_id,
        )
    except FlickrError as exc:
        return {"error": str(exc)}
    album = data.get("photoset", {})
    return {"album_id": album.get("id"), "url": album.get("url")}


@mcp.tool()
def add_photo_to_album(album_id: str, photo_id: str) -> Dict[str, Any]:
    """Add an existing photo to an existing album."""
    try:
        _client().call(
            "flickr.photosets.addPhoto",
            http="POST",
            photoset_id=album_id,
            photo_id=photo_id,
        )
    except FlickrError as exc:
        return {"error": str(exc)}
    return {"album_id": album_id, "photo_id": photo_id, "added": True}


@mcp.tool()
def set_photo_meta(
    photo_id: str, title: Optional[str] = None, description: Optional[str] = None
) -> Dict[str, Any]:
    """Update a photo's title and/or description. Flickr's setMeta requires the
    title, so an existing title is fetched when only description is supplied."""
    client = _client()
    if title is None:
        try:
            info = client.call("flickr.photos.getInfo", photo_id=photo_id)
            title = info.get("photo", {}).get("title", {}).get("_content", "")
        except FlickrError as exc:
            return {"error": str(exc)}
    try:
        client.call(
            "flickr.photos.setMeta",
            http="POST",
            photo_id=photo_id,
            title=title,
            description=description or "",
        )
    except FlickrError as exc:
        return {"error": str(exc)}
    return {"photo_id": photo_id, "title": title, "updated": True}


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
