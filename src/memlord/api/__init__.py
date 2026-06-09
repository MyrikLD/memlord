from fastapi import APIRouter

from .api_keys import router as api_keys_router
from .memories import router as memories_router
from .search import router as search_router
from .workspaces import router as workspaces_router

router = APIRouter(prefix="/api", tags=["API"])
router.include_router(api_keys_router)
router.include_router(memories_router)
router.include_router(search_router)
router.include_router(workspaces_router)
