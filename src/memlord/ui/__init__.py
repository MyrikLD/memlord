from fastapi import APIRouter

from .account import router as account_router
from .base import router
from .login import router as login_router
from .workspaces import router as workspaces_router

ui_router = APIRouter(prefix="/ui")
ui_router.include_router(login_router)
ui_router.include_router(workspaces_router)
ui_router.include_router(account_router)
router.include_router(ui_router)
