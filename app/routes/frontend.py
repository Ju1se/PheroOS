from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter(tags=["frontend"])
STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"


@router.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html")
