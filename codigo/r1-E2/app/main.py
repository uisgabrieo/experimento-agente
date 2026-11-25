"""Ponto de entrada da aplicacao.

Expoe o objeto ``app`` (FastAPI) exigido pela secao 2 da especificacao,
registra os roteadores e padroniza as respostas de erro (RF37: toda
resposta 4xx carrega a chave ``detail``).

Tambem instala o intermediario de auditoria, que registra as operacoes de
escrita em :mod:`app.auditoria`. A autenticacao por perfil fica em
:mod:`app.seguranca` e e aplicada como dependencia dos roteadores.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .auditoria import intermediario_de_auditoria
from .config import DESCRICAO, TITULO
from .erros import ErroDeNegocio
from .modelos import criar_tabelas
from .rotas import ROTEADORES

app = FastAPI(title=TITULO, description=DESCRICAO, version=__version__)

# O esquema e criado na importacao do modulo para que o aplicativo esteja
# pronto para uso tanto via servidor ASGI quanto via TestClient.
criar_tabelas()

for roteador, dependencias in ROTEADORES:
    app.include_router(roteador, dependencies=list(dependencias))

# O registro de auditoria fica na borda da aplicacao para observar o codigo
# final da resposta, inclusive os 4xx.
app.middleware("http")(intermediario_de_auditoria)


# --------------------------------------------------------------------------
# Manipuladores de erro (RF37)
# --------------------------------------------------------------------------
@app.exception_handler(ErroDeNegocio)
async def tratar_erro_de_negocio(
    _requisicao: Request, excecao: ErroDeNegocio
) -> JSONResponse:
    """Erros de dominio (404, 409 e 422) com mensagem em ``detail``."""

    return JSONResponse(
        status_code=excecao.status, content={"detail": excecao.detalhe}
    )


@app.exception_handler(StarletteHTTPException)
async def tratar_http(
    _requisicao: Request, excecao: StarletteHTTPException
) -> JSONResponse:
    """Garante a chave ``detail`` em qualquer erro HTTP."""

    detalhe = excecao.detail if excecao.detail else "erro na requisicao"
    return JSONResponse(
        status_code=excecao.status_code,
        content={"detail": jsonable_encoder(detalhe)},
        headers=getattr(excecao, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def tratar_validacao(
    _requisicao: Request, excecao: RequestValidationError
) -> JSONResponse:
    """Dados invalidos resultam em 422 com ``detail`` detalhado."""

    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(excecao.errors())},
    )


@app.exception_handler(IntegrityError)
async def tratar_integridade(
    _requisicao: Request, excecao: IntegrityError
) -> JSONResponse:
    """Conflitos detectados pelo banco (unicidade, chave estrangeira)."""

    return JSONResponse(
        status_code=409,
        content={"detail": f"conflito de integridade: {excecao.orig}"},
    )
