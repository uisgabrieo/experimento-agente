"""RF38 - verificacao de saude da aplicacao."""

from __future__ import annotations

from fastapi import APIRouter

roteador = APIRouter(tags=["saude"])


@roteador.get("/saude", summary="Verificar saude da aplicacao")
def verificar_saude() -> dict[str, str]:
    """Retorna exatamente ``{"status": "ok"}``."""

    return {"status": "ok"}
