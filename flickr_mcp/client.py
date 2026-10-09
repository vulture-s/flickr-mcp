"""Thin Flickr REST + upload client (OAuth 1.0a signed).

All read/write API calls go through the REST endpoint; photo upload uses the
separate upload endpoint (which returns XML, not JSON). Signing is handled by
requests-oauthlib's OAuth1Session so every call carries the user's access token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests
from requests_oauthlib import OAuth1Session

REST_URL = "https://api.flickr.com/services/rest/"
UPLOAD_URL = "https://up.flickr.com/services/upload/"

# (connect, read) seconds for REST calls. requests has no default timeout, so a
# half-open connection used to hang the MCP tool forever with no error.
REST_TIMEOUT = (10, 60)


class FlickrError(RuntimeError):
    """Raised when Flickr returns stat != ok, or credentials are missing."""


class MissingCredentials(FlickrError):
    """Raised when the four OAuth env vars are not all present."""


ENV_KEYS = (
    "FLICKR_API_KEY",
    "FLICKR_API_SECRET",
    "FLICKR_OAUTH_TOKEN",
    "FLICKR_OAUTH_TOKEN_SECRET",
)


class FlickrClient:
    """Signed Flickr client. Reads the four credentials from the environment
    unless they are passed explicitly (the authorize helper passes them in)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        oauth_token: Optional[str] = None,
        oauth_token_secret: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("FLICKR_API_KEY")
        self.api_secret = api_secret or os.environ.get("FLICKR_API_SECRET")
        self.oauth_token = oauth_token or os.environ.get("FLICKR_OAUTH_TOKEN")
        self.oauth_token_secret = (
            oauth_token_secret or os.environ.get("FLICKR_OAUTH_TOKEN_SECRET")
        )
        missing = [
            name
            for name, val in zip(
                ENV_KEYS,
                (
                    self.api_key,
                    self.api_secret,
                    self.oauth_token,
                    self.oauth_token_secret,
                ),
            )
            if not val
        ]
        if missing:
            raise MissingCredentials(
                "Missing Flickr credentials: "
                + ", ".join(missing)
                + ". Run authorize.py and export the four FLICKR_* vars."
            )

    def _session(self) -> OAuth1Session:
        return OAuth1Session(
            self.api_key,
            client_secret=self.api_secret,
            resource_owner_key=self.oauth_token,
            resource_owner_secret=self.oauth_token_secret,
        )

    def call(self, method: str, http: str = "GET", **params: Any) -> Dict[str, Any]:
        """Call a Flickr REST method and return the parsed JSON payload.

        Extra kwargs become method params (None values are dropped). Raises
        FlickrError on a non-ok response.
        """
        query = {
            "method": method,
            "format": "json",
            "nojsoncallback": "1",
        }
        for key, val in params.items():
            if val is not None:
                query[key] = val

        session = self._session()
        if http.upper() == "POST":
            resp = session.post(REST_URL, data=query, timeout=REST_TIMEOUT)
        else:
            resp = session.get(REST_URL, params=query, timeout=REST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("stat") != "ok":
            raise FlickrError(
                f"{method} failed: {data.get('message')} (code {data.get('code')})"
            )
        return data

    def _sign_upload(self, params: Dict[str, Any]) -> Dict[str, str]:
        """OAuth-1.0a-sign the upload params (HMAC-SHA1, UTF-8 safe) and return them
        plus the oauth_* fields, ready to POST as multipart form fields alongside the
        photo. requests-oauthlib does not sign multipart bodies (the file part makes it
        drop the params), which returns 401 — so the signature is built by hand here.
        """
        oauth = {
            "oauth_consumer_key": self.api_key,
            "oauth_token": self.oauth_token,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_nonce": uuid.uuid4().hex,
            "oauth_version": "1.0",
        }
        enc = lambda s: quote(str(s), safe="~")
        merged = {**params, **oauth}
        norm = "&".join(f"{enc(k)}={enc(merged[k])}" for k in sorted(merged))
        base = "&".join(["POST", enc(UPLOAD_URL), enc(norm)])
        key = f"{enc(self.api_secret)}&{enc(self.oauth_token_secret)}"
        oauth["oauth_signature"] = base64.b64encode(
            hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
        ).decode()
        return {**{k: str(v) for k, v in params.items()}, **oauth}

    def upload(
        self,
        photo_path: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[str] = None,
        is_public: int = 0,
    ) -> str:
        """Upload a local image file; return the new photo id.

        Defaults to private (is_public=0) so nothing goes public by accident.
        The upload endpoint replies with XML, so we parse that rather than JSON.
        """
        if not os.path.isfile(photo_path):
            raise FlickrError(f"File not found: {photo_path}")

        data = {"is_public": str(is_public)}
        if title is not None:
            data["title"] = title
        if description is not None:
            data["description"] = description
        if tags is not None:
            data["tags"] = tags

        signed = self._sign_upload(data)
        with open(photo_path, "rb") as fh:
            resp = requests.post(UPLOAD_URL, data=signed, files={"photo": fh})
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        if root.attrib.get("stat") != "ok":
            err = root.find("err")
            msg = err.attrib.get("msg") if err is not None else resp.text
            raise FlickrError(f"upload failed: {msg}")
        photoid = root.findtext("photoid")
        if not photoid:
            raise FlickrError(f"upload ok but no photoid in response: {resp.text}")
        return photoid
