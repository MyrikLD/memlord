"""Tests for the OAuth auth pipeline.

Specifically guards against the bug where JWT aud=base_url instead of
aud=resource_url (base_url + mcp_path). Clients like claude.ai validate
the JWT audience against the resource indicator; a mismatch causes them
to drop the Bearer token, resulting in 401 on every MCP request.
"""

import base64
import hashlib
import secrets
import time

import pytest
from authlib.jose import JsonWebToken
from mcp.server.auth.provider import AuthorizationCode, AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl, AnyUrl

from mnemos.oauth import MnemosOAuthProvider

BASE_URL = "https://mcp.example.com"
MCP_PATH = "/mcp"
RESOURCE_URL = f"{BASE_URL}{MCP_PATH}"


@pytest.fixture
def provider():
    return MnemosOAuthProvider(
        base_url=BASE_URL,
        jwt_secret="test-only-secret",
        password="hunter2",
    )


@pytest.fixture
def oauth_client():
    return OAuthClientInformationFull(
        client_id="test-client",
        redirect_uris=[AnyHttpUrl("https://client.example.com/callback")],
        scope="mcp",
    )


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


async def test_full_auth_pipeline_jwt_audience(provider, oauth_client):
    """Full OAuth pipeline: set_mcp_path → authorize → exchange → validate.

    The critical assertion is that the issued token's `aud` claim equals
    the resource URL (BASE_URL + MCP_PATH), not just BASE_URL.  The bug
    this test prevents: jwt.audience was never updated when the MCP path
    was registered, so tokens had aud=base_url.  Clients that validate
    the JWT audience against the resource indicator would then discard
    the token and never send a Bearer header, causing a permanent 401.
    """
    # Simulate what mcp.http_app(path="/mcp") triggers internally.
    provider.set_mcp_path(MCP_PATH)

    verifier, challenge = _pkce_pair()

    params = AuthorizationParams(
        state="test-state",
        scopes=["mcp"],
        code_challenge=challenge,
        redirect_uri=AnyUrl("https://client.example.com/callback"),
        redirect_uri_provided_explicitly=True,
        resource=RESOURCE_URL,
    )

    # authorize() stores pending auth and returns the login URL.
    login_url = await provider.authorize(oauth_client, params)
    assert "/login?id=" in login_url
    pending_id = login_url.split("id=")[1]

    # Simulate a successful password submission: pop pending and create auth code.
    pending = provider._pending.pop(pending_id)
    code = secrets.token_urlsafe(32)
    provider._auth_codes[code] = AuthorizationCode(
        code=code,
        client_id=pending.client_id,
        redirect_uri=pending.params.redirect_uri,
        redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
        scopes=pending.scopes,
        expires_at=time.time() + 300,
        code_challenge=pending.params.code_challenge,
        resource=pending.params.resource,
    )

    # Exchange the auth code for an OAuth token pair.
    auth_code = await provider.load_authorization_code(oauth_client, code)
    assert auth_code is not None, "auth code should be retrievable"
    assert auth_code.resource == RESOURCE_URL, "resource must be preserved in auth code"

    oauth_token = await provider.exchange_authorization_code(oauth_client, auth_code)
    access_token_str = oauth_token.access_token

    # --- Key assertion: JWT aud must be the resource URL, not just base_url ---
    raw_jwt = JsonWebToken(["HS256"])
    payload = raw_jwt.decode(access_token_str, provider._signing_key)

    assert payload["aud"] == RESOURCE_URL, (
        f"JWT aud must equal the resource URL '{RESOURCE_URL}' "
        f"but got '{payload['aud']}'. "
        "Clients validate aud against the resource indicator; a mismatch causes "
        "them to silently drop the token and make unauthenticated requests."
    )
    assert payload["iss"] == BASE_URL

    # --- load_access_token must accept the issued token ---
    access_token = await provider.load_access_token(access_token_str)
    assert access_token is not None, "load_access_token must accept the issued token"
    assert "mcp" in access_token.scopes
    assert access_token.client_id == oauth_client.client_id
