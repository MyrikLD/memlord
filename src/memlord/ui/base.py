from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from memlord.ui.utils import APIUserDep, templates

router = APIRouter(tags=["UI"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: APIUserDep) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"user": user})


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    user: APIUserDep,
    query: str = Query('', alias="q"),
) -> HTMLResponse:
    return templates.TemplateResponse(request, "search.html", {"user": user, "query": query})


@router.get("/memory/{workspace_id}/{memory_id}", response_class=HTMLResponse)
async def memory_detail(
    request: Request,
    workspace_id: int,
    memory_id: int,
    user: APIUserDep,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "memory.html",
        {"user": user, "workspace_id": workspace_id, "memory_id": memory_id},
    )
