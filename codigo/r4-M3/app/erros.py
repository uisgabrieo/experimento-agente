"""Padronizacao de erros (RF37).

Toda resposta 4xx produzida pela aplicacao carrega a chave ``detail``.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def nao_encontrado(mensagem: str) -> HTTPException:
    """Erro 404 padronizado."""

    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=mensagem)


def conflito(mensagem: str) -> HTTPException:
    """Erro 409 padronizado (violacao de invariante ou de regra de negocio)."""

    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=mensagem)


def registrar_tratadores(app: FastAPI) -> None:
    """Instala os tratadores de excecao que garantem o formato dos erros."""

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detalhe = exc.detail if exc.detail is not None else "erro"
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detalhe},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validacao(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": _serializar_erros(exc.errors())},
        )


def _serializar_erros(erros: list[dict]) -> list[dict]:
    """Remove objetos nao serializaveis do relatorio de validacao."""

    limpos: list[dict] = []
    for erro in erros:
        item = {chave: valor for chave, valor in erro.items() if chave != "ctx"}
        item["loc"] = [str(parte) for parte in erro.get("loc", ())]
        if "input" in item:
            item["input"] = _seguro(item["input"])
        limpos.append(item)
    return limpos


def _seguro(valor: object) -> object:
    if isinstance(valor, (str, int, float, bool, type(None))):
        return valor
    if isinstance(valor, dict):
        return {str(chave): _seguro(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_seguro(item) for item in valor]
    return str(valor)
