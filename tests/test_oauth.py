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
from contextlib import asynccontextmanager

import pytest
from authlib.jose import JsonWebToken
from mcp.server.auth.provider import AuthorizationCode, AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl, AnyUrl

from memlord.oauth import MemlordOAuthProvider

BASE_URL = "https://mcp.example.com"
MCP_PATH = "/mcp"
RESOURCE_URL = f"{BASE_URL}{MCP_PATH}"


@pytest.fixture
def provider(session):
    @asynccontextmanager
    async def session_factory():
        yield session

    return MemlordOAuthProvider(
        base_url=BASE_URL,
        jwt_secret="test-only-secret",
        session_factory=session_factory,
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
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    return verifier, challenge


async def test_full_auth_pipeline_jwt_audience(provider, oauth_client, session):
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


@pytest.fixture
async def pending_id(provider, oauth_client):
    oauth_client.client_name = '<b>Evil</b> "App"'
    await provider.register_client(oauth_client)
    _, challenge = _pkce_pair()
    params = AuthorizationParams(
        state="st",
        scopes=["mcp"],
        code_challenge=challenge,
        redirect_uri=AnyUrl("https://client.example.com/callback"),
        redirect_uri_provided_explicitly=True,
        resource=RESOURCE_URL,
    )
    login_url = await provider.authorize(oauth_client, params)
    return login_url.split("id=")[1]


async def _login(provider, pending_id: str):
    form = {"email": "test@example.com", "password": "test-password"}
    return await provider._handle_login(form, pending_id, provider._pending[pending_id])


async def _consent(provider, pending_id: str, decision: str):
    form = {"decision": decision}
    return await provider._handle_consent(form, pending_id, provider._pending[pending_id])


async def test_login_shows_consent_instead_of_code(provider, pending_id, user_id):
    resp = await _login(provider, pending_id)

    assert resp.status_code == 200
    body = bytes(resp.body).decode()
    assert "Authorize access" in body
    assert "client.example.com" in body
    assert "&lt;b&gt;Evil&lt;/b&gt;" in body
    assert "<b>Evil</b>" not in body
    assert resp.headers["x-frame-options"] == "DENY"
    assert provider._auth_codes == {}


async def test_consent_allow_issues_code(provider, pending_id, user_id):
    await _login(provider, pending_id)
    resp = await _consent(provider, pending_id, "allow")

    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://client.example.com/callback?code=")
    assert len(provider._auth_codes) == 1
    assert pending_id not in provider._pending


async def test_consent_deny_redirects_with_error(provider, pending_id, user_id):
    await _login(provider, pending_id)
    resp = await _consent(provider, pending_id, "deny")

    assert resp.status_code == 302
    assert "error=access_denied" in resp.headers["location"]
    assert "state=st" in resp.headers["location"]
    assert provider._auth_codes == {}
    assert pending_id not in provider._pending


async def test_consent_requires_full_login(provider, pending_id, user_id):
    # Password passed but TOTP not yet verified: consent must be refused.
    provider._pending[pending_id].authenticated_user_id = user_id
    resp = await _consent(provider, pending_id, "allow")

    assert resp.status_code == 400
    assert provider._auth_codes == {}


async def test_login_page_escapes_email(provider, pending_id):
    form = {"email": '"><script>alert(1)</script>', "password": "x"}
    resp = await provider._handle_login(form, pending_id, provider._pending[pending_id])

    body = bytes(resp.body).decode()
    assert "<script>" not in body
    assert "&lt;script&gt;" in body
