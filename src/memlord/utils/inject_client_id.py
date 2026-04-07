from urllib.parse import parse_qs, urlencode

from starlette.types import ASGIApp, Receive, Scope, Send


class InjectClientIdMiddleware:
    """Starlette ASGI middleware that injects client_id into /token form body when absent."""

    def __init__(self, app: ASGIApp, *, auth_codes: dict) -> None:
        self.app = app
        self._auth_codes = auth_codes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/token":
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        more = True
        while more:
            msg = await receive()
            chunks.append(msg.get("body", b""))
            more = msg.get("more_body", False)
        body = b"".join(chunks)

        params = {k: v[0] for k, v in parse_qs(body.decode(), keep_blank_values=True).items()}
        if not params.get("client_id") and params.get("code"):
            entry = self._auth_codes.get(params["code"])
            if entry:
                params["client_id"] = entry.client_id
                body = urlencode(params).encode()

        headers = [(k, v) for k, v in scope["headers"] if k != b"content-length"]
        headers += [
            (b"content-length", str(len(body)).encode()),
        ]

        consumed = False

        async def _receive() -> dict:
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app({**scope, "headers": headers}, _receive, send)
