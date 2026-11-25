"""Ponto de entrada da aplicacao.

Expoe o objeto ``app`` exigido pela secao 2 da especificacao.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.config import TITULO_API, VERSAO_API
from app.db import criar_tabelas
from app.erros import registrar_tratadores
from app.rotas import ROTEADORES


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
    """Garante o esquema do banco antes de atender requisicoes."""

    criar_tabelas()
    yield


app = FastAPI(
    title=TITULO_API,
    version=VERSAO_API,
    description=(
        "API de organizacao da escala mensal de plantoes de uma clinica, "
        "com controle de jornada, cobertura, trocas e substituicoes."
    ),
    lifespan=ciclo_de_vida,
)

registrar_tratadores(app)

for roteador in ROTEADORES:
    app.include_router(roteador)


# O esquema tambem e criado na importacao do modulo, de modo que clientes de
# teste que nao disparem os eventos de ciclo de vida encontrem as tabelas
# prontas.
criar_tabelas()


@app.get("/", include_in_schema=False)
def raiz() -> dict[str, str]:
    """Identificacao basica do servico."""

    return {"servico": TITULO_API, "versao": VERSAO_API}
