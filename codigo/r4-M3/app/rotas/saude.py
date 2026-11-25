"""RF38 - verificacao de saude da aplicacao."""

from __future__ import annotations

from fastapi import APIRouter, status

roteador = APIRouter(tags=["saude"])


@roteador.get("/saude", status_code=status.HTTP_200_OK)
def saude() -> dict[str, str]:
    """Retorna exatamente ``{"status": "ok"}``."""

    return {"status": "ok"}
