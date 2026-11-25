"""RF38 - verificacao de saude da aplicacao."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["saude"])


@router.get("/saude", summary="RF38 - verificar saude da aplicacao")
def saude() -> dict[str, str]:
    """Responde exatamente ``{"status": "ok"}``."""

    return {"status": "ok"}
