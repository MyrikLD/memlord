import asyncio
from argparse import ArgumentParser
from contextlib import asynccontextmanager
from pathlib import Path

import sqlalchemy as sa
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette import status

from memlord.config import settings
from memlord.db import session
from memlord.server import mcp
from memlord.ui import router as ui_router

mcp_app = mcp.http_app(path="/mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_app.lifespan(mcp_app):
        yield


app = FastAPI(title="Memlord", lifespan=lifespan)


@app.exception_handler(PermissionError)
async def permission_error_handler(
    request: Request, exc: PermissionError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc)},
    )


_FAVICON = Path(__file__).parent / "templates" / "icon.svg"


@app.get("/favicon.svg", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(_FAVICON, media_type="image/svg+xml")


@app.get("/health")
async def health() -> JSONResponse:
    try:
        async with session() as s:
            await s.execute(sa.text("SELECT 1"))
        return JSONResponse({"status": "ok"})
    except Exception as exc:
        return JSONResponse(
            {"status": "error", "detail": str(exc)},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# UI routes must be registered BEFORE the root mount so they take priority.
app.include_router(ui_router)
# Mount mcp_app at "/" so that OAuth /.well-known/* endpoints are at the root,
# matching what MCP clients expect.  The MCP transport itself is at /mcp.
app.mount("/", mcp_app)


def main():
    parser = ArgumentParser(prog="Memlord")
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args()

    if args.stdio:
        asyncio.run(mcp.run_stdio_async())
    else:
        uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
