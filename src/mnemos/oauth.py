import logging
import secrets
import time
from urllib.parse import urlencode

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from pydantic import BaseModel

from mnemos.db import session
from mnemos.models.oauth_client import OAuthClient

from authlib.jose.errors import JoseError
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from fastmcp.server.auth import OAuthProvider
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.jwt_issuer import JWTIssuer, derive_jwt_key

logger = logging.getLogger(__name__)

ACCESS_TOKEN_TTL = 3600  # 1 hour
REFRESH_TOKEN_TTL = 30 * 24 * 3600  # 30 days
AUTH_CODE_TTL = 300  # 5 minutes
PENDING_TTL = 600  # 10 minutes to complete login

_LOGIN_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mnemos — Sign in</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, sans-serif; background: #f5f5f5; color: #111;
           display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
    .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
             padding: 2rem; width: 100%; max-width: 360px;
             box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
    h1 {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 1.5rem; color: #111; }}
    label {{ display: block; font-size: 0.875rem; color: #555; margin-bottom: 0.375rem; }}
    input[type=password] {{ width: 100%; padding: 0.625rem 0.75rem;
                            border: 1px solid #d1d5db; border-radius: 6px; color: #111;
                            font-size: 0.875rem; outline: none; }}
    input[type=password]:focus {{ border-color: #6366f1; }}
    button {{ width: 100%; margin-top: 1.25rem; padding: 0.625rem;
              background: #6366f1; border: none; border-radius: 6px;
              color: #fff; font-size: 0.875rem; font-weight: 500; cursor: pointer; }}
    button:hover {{ background: #4f46e5; }}
    .error {{ margin-top: 1rem; padding: 0.5rem 0.75rem; background: #fef2f2;
              border: 1px solid #f87171; border-radius: 6px;
              color: #dc2626; font-size: 0.8125rem; }}
    .meta {{ margin-top: 1rem; font-size: 0.75rem; color: #9ca3af; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Mnemos</h1>
    <form method="post">
      <input type="hidden" name="id" value="{pending_id}">
      <label for="pw">Password</label>
      <input type="password" id="pw" name="password" autofocus required
             autocomplete="current-password">
      <button type="submit">Sign in</button>
      {error_block}
    </form>
    <p class="meta">Client: {client_id}</p>
  </div>
</body>
</html>
"""


class _PendingAuth(BaseModel):
    client_id: str
    params: AuthorizationParams
    scopes: list[str]
    expires_at: float


class MnemosOAuthProvider(OAuthProvider):
    """Full in-process OAuth 2.1 authorization server with password login page."""

    def __init__(self, base_url: str, jwt_secret: str, password: str) -> None:
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["mcp"],
                default_scopes=["mcp"],
            ),
            revocation_options=RevocationOptions(enabled=True),
            required_scopes=["mcp"],
        )
        self._base_url = base_url.rstrip("/")
        self._password = password

        self._signing_key = derive_jwt_key(
            high_entropy_material=jwt_secret, salt="mnemos-oauth-jwt"
        )
        self._jwt = JWTIssuer(
            issuer=self._base_url,
            audience=self._base_url,
            signing_key=self._signing_key,
        )

        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}  # jti → AccessToken
        self._refresh_tokens: dict[str, RefreshToken] = {}  # raw token → RefreshToken
        self._token_to_jti: dict[str, str] = {}  # access token str → jti
        self._access_to_refresh: dict[str, str] = {}  # access str → refresh str
        self._refresh_to_access: dict[str, str] = {}  # refresh str → access str
        self._pending: dict[str, _PendingAuth] = {}

    # ------------------------------------------------------------------
    # Login page
    # ------------------------------------------------------------------

    def set_mcp_path(self, mcp_path: str | None) -> None:
        super().set_mcp_path(mcp_path)
        # Update JWT audience to the resource URL now that the MCP path is known.
        # Per RFC 8707, tokens must be bound to the resource they are issued for.
        audience = (
            str(self._resource_url).rstrip("/")
            if self._resource_url is not None
            else self._base_url
        )
        self._jwt = JWTIssuer(
            issuer=self._base_url,
            audience=audience,
            signing_key=self._signing_key,
        )
        logger.debug("set_mcp_path: JWT audience updated to %s", audience)

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        routes = super().get_routes(mcp_path)
        routes += [Route("/login", endpoint=self._login, methods=["GET", "POST"])]

        # RFC 9728: clients discover metadata via path-based URL first, then fall back to
        # root-based /.well-known/oauth-protected-resource. Alias the path-specific route
        # at root so both work.
        for route in list(routes):
            if isinstance(route, Route) and route.path.startswith(
                "/.well-known/oauth-protected-resource/"
            ):
                routes.append(
                    Route(
                        "/.well-known/oauth-protected-resource",
                        endpoint=route.endpoint,
                        methods=["GET", "OPTIONS"],
                    )
                )
                break

        return routes

    async def _login(self, request: Request) -> Response:
        if request.method == "GET":
            return self._login_get(request)
        return await self._login_post(request)

    def _login_get(self, request: Request) -> Response:
        pending_id = request.query_params.get("id", "")
        pending = self._pending.get(pending_id)
        if not pending or pending.expires_at < time.time():
            logger.warning(
                "login GET: invalid/expired pending_id=%s...", pending_id[:8]
            )
            return HTMLResponse(
                "<h3>Authorization request expired. Please try again.</h3>",
                status_code=400,
            )
        return HTMLResponse(
            _LOGIN_HTML.format(
                pending_id=pending_id,
                client_id=pending.client_id,
                error_block="",
            )
        )

    async def _login_post(self, request: Request) -> Response:
        form = await request.form()
        pending_id = str(form.get("id", ""))
        password = str(form.get("password", ""))

        pending = self._pending.get(pending_id)
        if not pending or pending.expires_at < time.time():
            self._pending.pop(pending_id, None)
            logger.warning(
                "login POST: invalid/expired pending_id=%s...", pending_id[:8]
            )
            return HTMLResponse(
                "<h3>Authorization request expired. Please try again.</h3>",
                status_code=400,
            )

        if not secrets.compare_digest(password.encode(), self._password.encode()):
            logger.warning("login POST: wrong password client_id=%s", pending.client_id)
            return HTMLResponse(
                _LOGIN_HTML.format(
                    pending_id=pending_id,
                    client_id=pending.client_id,
                    error_block='<p class="error">Incorrect password.</p>',
                ),
                status_code=401,
            )

        del self._pending[pending_id]

        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = AuthorizationCode(
            code=code,
            client_id=pending.client_id,
            redirect_uri=pending.params.redirect_uri,
            redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
            scopes=pending.scopes,
            expires_at=time.time() + AUTH_CODE_TTL,
            code_challenge=pending.params.code_challenge,
            resource=pending.params.resource,
        )
        redirect = construct_redirect_uri(
            str(pending.params.redirect_uri), code=code, state=pending.params.state
        )
        logger.info(
            "login POST: success client_id=%s code=%s...", pending.client_id, code[:8]
        )
        return RedirectResponse(redirect, status_code=302)

    # ------------------------------------------------------------------
    # OAuthAuthorizationServerProvider
    # ------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with session() as s:
            data = await s.scalar(
                sa.select(OAuthClient.data).where(OAuthClient.client_id == client_id)
            )

        if data is None:
            return None

        return OAuthClientInformationFull.model_validate(data)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if client_info.client_id is None:
            raise ValueError("client_id required")
        logger.info(
            "register_client client_id=%s redirect_uris=%s scope=%s",
            client_info.client_id,
            client_info.redirect_uris,
            client_info.scope,
        )
        data = client_info.model_dump(mode="json")
        async with session() as s:
            await s.execute(
                sqlite_insert(OAuthClient)
                .values(client_id=client_info.client_id, data=data)
                .on_conflict_do_update(
                    index_elements=[OAuthClient.client_id],
                    set_={"data": data},
                )
            )

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if client.client_id is None:
            raise AuthorizeError(
                error="unauthorized_client",
                error_description="Missing client_id",
            )

        scopes = list(params.scopes or [])
        if client.scope:
            allowed = set(client.scope.split())
            scopes = [s for s in scopes if s in allowed] or list(allowed)

        pending_id = secrets.token_urlsafe(32)
        self._pending[pending_id] = _PendingAuth(
            client_id=client.client_id,
            params=params,
            scopes=scopes,
            expires_at=time.time() + PENDING_TTL,
        )
        login_url = f"{self._base_url}/login?{urlencode({'id': pending_id})}"
        logger.info(
            "authorize → login client_id=%s pending=%s...",
            client.client_id,
            pending_id[:8],
        )
        return login_url

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        entry = self._auth_codes.get(authorization_code)
        if not entry or entry.client_id != client.client_id:
            return None
        if entry.expires_at < time.time():
            del self._auth_codes[authorization_code]
            return None
        return entry

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.code not in self._auth_codes:
            raise TokenError("invalid_grant", "Code already used or expired")
        del self._auth_codes[authorization_code.code]
        if client.client_id is None:
            raise TokenError("invalid_client", "Missing client_id")
        token = self._issue_token_pair(client.client_id, authorization_code.scopes)
        logger.info(
            "exchange_authorization_code issued access=%s... scopes=%s",
            token.access_token[:16],
            token.scope,
        )
        return token

    async def load_access_token(self, token: str) -> AccessToken | None:  # type: ignore[override]
        try:
            claims = self._jwt.verify_token(token)
        except JoseError as exc:
            logger.debug("load_access_token JWT invalid: %s", exc)
            return None
        jti = claims.get("jti")
        if not jti:
            return None
        stored = self._access_tokens.get(jti)
        if stored is not None:
            return stored
        # Fallback: reconstruct from JWT claims after server restart.
        # Revocation is best-effort — revoked tokens may become valid again after restart.
        client_id = claims.get("client_id", "")
        scopes = claims.get("scope", "").split() if claims.get("scope") else []
        exp = claims.get("exp")
        logger.debug(
            "load_access_token: reconstructing from JWT claims (post-restart) jti=%s...",
            jti[:8],
        )
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(exp) if exp else None,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        entry = self._refresh_tokens.get(refresh_token)
        if entry:
            if entry.client_id != client.client_id:
                return None
            if entry.expires_at is not None and entry.expires_at < time.time():
                del self._refresh_tokens[refresh_token]
                return None
            return entry
        # Fallback: verify as JWT and reconstruct after server restart.
        try:
            claims = self._jwt.verify_token(refresh_token)
        except JoseError as exc:
            logger.debug("load_refresh_token JWT invalid: %s", exc)
            return None
        if claims.get("token_use") != "refresh":
            return None
        token_client_id = claims.get("client_id", "")
        if token_client_id != client.client_id:
            return None
        scopes = claims.get("scope", "").split() if claims.get("scope") else []
        exp = claims.get("exp")
        logger.debug(
            "load_refresh_token: reconstructing from JWT claims (post-restart) client_id=%s",
            token_client_id,
        )
        return RefreshToken(
            token=refresh_token,
            client_id=token_client_id,
            scopes=scopes,
            expires_at=int(exp) if exp else None,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        if scopes and not set(scopes).issubset(set(refresh_token.scopes)):
            raise TokenError("invalid_scope", "Requested scopes exceed original grant")
        effective_scopes = scopes or refresh_token.scopes
        self._revoke_pair(refresh_token_str=refresh_token.token)
        if client.client_id is None:
            raise TokenError("invalid_client", "Missing client_id")
        token = self._issue_token_pair(client.client_id, effective_scopes)
        logger.info(
            "exchange_refresh_token issued access=%s... scopes=%s",
            token.access_token[:16],
            token.scope,
        )
        return token

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:  # type: ignore[override]
        logger.info("revoke_token type=%s", type(token).__name__)
        if isinstance(token, AccessToken):
            self._revoke_pair(access_token_str=token.token)
        else:
            self._revoke_pair(refresh_token_str=token.token)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _issue_token_pair(self, client_id: str, scopes: list[str]) -> OAuthToken:
        now = int(time.time())

        jti = secrets.token_urlsafe(32)
        access_str = self._jwt.issue_access_token(
            client_id=client_id, scopes=scopes, jti=jti, expires_in=ACCESS_TOKEN_TTL
        )
        self._access_tokens[jti] = AccessToken(
            token=access_str,
            client_id=client_id,
            scopes=scopes,
            expires_at=now + ACCESS_TOKEN_TTL,
        )
        self._token_to_jti[access_str] = jti

        refresh_jti = secrets.token_urlsafe(32)
        refresh_str = self._jwt.issue_refresh_token(
            client_id=client_id,
            scopes=scopes,
            jti=refresh_jti,
            expires_in=REFRESH_TOKEN_TTL,
        )
        self._refresh_tokens[refresh_str] = RefreshToken(
            token=refresh_str,
            client_id=client_id,
            scopes=scopes,
            expires_at=now + REFRESH_TOKEN_TTL,
        )
        self._access_to_refresh[access_str] = refresh_str
        self._refresh_to_access[refresh_str] = access_str

        return OAuthToken(
            access_token=access_str,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=refresh_str,
            scope=" ".join(scopes),
        )

    def _revoke_pair(
        self,
        access_token_str: str | None = None,
        refresh_token_str: str | None = None,
    ) -> None:
        if access_token_str:
            jti = self._token_to_jti.pop(access_token_str, None)
            if jti:
                self._access_tokens.pop(jti, None)
            paired_refresh = self._access_to_refresh.pop(access_token_str, None)
            if paired_refresh:
                self._refresh_tokens.pop(paired_refresh, None)
                self._refresh_to_access.pop(paired_refresh, None)

        if refresh_token_str:
            self._refresh_tokens.pop(refresh_token_str, None)
            paired_access = self._refresh_to_access.pop(refresh_token_str, None)
            if paired_access:
                jti = self._token_to_jti.pop(paired_access, None)
                if jti:
                    self._access_tokens.pop(jti, None)
                self._access_to_refresh.pop(paired_access, None)
