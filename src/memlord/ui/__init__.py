from fastapi import APIRouter

from .base import router
from .data import router as data_router
from .login import router as login_router
from .workspaces import router as workspaces_router

ui_router = APIRouter(prefix="/ui")
ui_router.include_router(data_router)
ui_router.include_router(login_router)
ui_router.include_router(workspaces_router)
router.include_router(ui_router)
