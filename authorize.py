#!/usr/bin/env python3
"""One-time Flickr OAuth 1.0a authorization (out-of-band / desktop flow).

Run this once to turn your app's API Key + Secret into a long-lived access
token that the MCP server uses. Steps:

    1. Create an app at https://www.flickr.com/services/apps/create/
       -> copy its Key and Secret.
    2. export FLICKR_API_KEY=...  FLICKR_API_SECRET=...
    3. python authorize.py
       -> open the printed URL, click "OK, I'll authorize it", copy the 9-digit
          code it shows, paste it back here.
    4. Export the two tokens it prints (FLICKR_OAUTH_TOKEN / _SECRET).

Requests 'delete' perms (covers read + upload + album management + delete). Nothing is
written to disk automatically; you paste the tokens into your MCP config.
"""

import os
import sys

from requests_oauthlib import OAuth1Session

REQUEST_TOKEN_URL = "https://www.flickr.com/services/oauth/request_token"
AUTHORIZE_URL = "https://www.flickr.com/services/oauth/authorize"
ACCESS_TOKEN_URL = "https://www.flickr.com/services/oauth/access_token"


def main() -> int:
    api_key = os.environ.get("FLICKR_API_KEY")
    api_secret = os.environ.get("FLICKR_API_SECRET")
    if not api_key or not api_secret:
        print(
            "ERROR: set FLICKR_API_KEY and FLICKR_API_SECRET first "
            "(from your app at flickr.com/services/apps/create).",
            file=sys.stderr,
        )
        return 1

    # Step 1: request token (oob = show verifier code in browser, no callback server)
    oauth = OAuth1Session(api_key, client_secret=api_secret, callback_uri="oob")
    fetch = oauth.fetch_request_token(REQUEST_TOKEN_URL)
    req_key = fetch.get("oauth_token")
    req_secret = fetch.get("oauth_token_secret")

    # Step 2: user authorizes (delete perms cover read + upload + album ops + delete)
    auth_url = oauth.authorization_url(AUTHORIZE_URL, perms="delete")
    print("\n1) Open this URL in your browser and approve access:\n")
    print("   " + auth_url + "\n")
    verifier = input("2) Paste the verification code shown by Flickr: ").strip()

    # Step 3: exchange for the long-lived access token
    oauth = OAuth1Session(
        api_key,
        client_secret=api_secret,
        resource_owner_key=req_key,
        resource_owner_secret=req_secret,
        verifier=verifier,
    )
    tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)
    access_token = tokens.get("oauth_token")
    access_secret = tokens.get("oauth_token_secret")

    print("\nSuccess. Add these to your MCP server config env "
          "(alongside the key/secret):\n")
    print(f"  FLICKR_API_KEY={api_key}")
    print(f"  FLICKR_API_SECRET={api_secret}")
    print(f"  FLICKR_OAUTH_TOKEN={access_token}")
    print(f"  FLICKR_OAUTH_TOKEN_SECRET={access_secret}")
    print(f"\n(Authorized as: {tokens.get('fullname') or tokens.get('username')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
