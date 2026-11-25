"""Ponto de entrada da aplicacao: objeto ``app`` do FastAPI."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import criar_esquema
from .erros import registrar_tratadores
from .routers import ROTEADORES

DESCRICAO = (
    "Organiza a escala mensal de plantoes respeitando os limites de jornada "
    "dos profissionais, as ausencias registradas e a fila de substituicoes. "
    "Datas e horarios sao sempre tratados em UTC, no formato ISO 8601."
)


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    criar_esquema()
    yield


def criar_app() -> FastAPI:
    """Monta a aplicacao: esquema, tratadores de erro e roteadores."""

    aplicacao = FastAPI(
        title="Escala de Plantao",
        description=DESCRICAO,
        version="1.0.0",
        lifespan=ciclo_de_vida,
    )

    registrar_tratadores(aplicacao)
    for roteador in ROTEADORES:
        aplicacao.include_router(roteador)

    @aplicacao.get("/", tags=["saude"], summary="Identificacao da aplicacao")
    def raiz() -> dict[str, str]:
        return {"aplicacao": "escala-de-plantao", "versao": aplicacao.version}

    return aplicacao


app = criar_app()

# O esquema tambem e criado na importacao: alguns clientes de teste acessam
# as rotas sem acionar o evento de ciclo de vida.
criar_esquema()
