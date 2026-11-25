"""Erros de dominio e padronizacao das respostas 4xx (RF37).

Toda resposta da classe 4xx produzida pela aplicacao carrega a chave
``detail``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErroDeDominio(HTTPException):
    """Base dos erros de negocio da aplicacao."""

    status_padrao = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(status_code=status_code or self.status_padrao, detail=detail)


class NaoEncontrado(ErroDeDominio):
    """Recurso inexistente (404)."""

    status_padrao = status.HTTP_404_NOT_FOUND


class Conflito(ErroDeDominio):
    """Violacao de regra de negocio ou de invariante (409)."""

    status_padrao = status.HTTP_409_CONFLICT


def nao_encontrado(recurso: str, identificador: Any) -> NaoEncontrado:
    """Monta o erro 404 padrao para um recurso e seu identificador."""

    return NaoEncontrado(f"{recurso} {identificador} nao encontrado")


def _resposta(status_code: int, detail: Any) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def registrar_tratadores(app: FastAPI) -> None:
    """Instala os tratadores de excecao que garantem o contrato RF37."""

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if exc.detail is not None else "erro"
        resposta = _resposta(exc.status_code, detail)
        if exc.headers:
            for chave, valor in exc.headers.items():
                resposta.headers[chave] = valor
        return resposta

    @app.exception_handler(RequestValidationError)
    async def _validacao(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _resposta(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            _normalizar_erros_de_validacao(exc.errors()),
        )

    @app.exception_handler(IntegrityError)
    async def _integridade(_request: Request, exc: IntegrityError) -> JSONResponse:
        return _resposta(
            status.HTTP_409_CONFLICT,
            f"violacao de integridade: {_mensagem_de_integridade(exc)}",
        )

    @app.exception_handler(ValueError)
    async def _valor(_request: Request, exc: ValueError) -> JSONResponse:
        return _resposta(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def _normalizar_erros_de_validacao(erros: list[Any]) -> list[dict[str, Any]]:
    """Deixa os erros do Pydantic serializaveis em JSON."""

    normalizados: list[dict[str, Any]] = []
    for erro in erros:
        item = {
            "type": erro.get("type"),
            "loc": [str(parte) for parte in erro.get("loc", ())],
            "msg": erro.get("msg"),
        }
        entrada = erro.get("input")
        if isinstance(entrada, (str, int, float, bool)) or entrada is None:
            item["input"] = entrada
        normalizados.append(item)
    return normalizados


def _mensagem_de_integridade(exc: IntegrityError) -> str:
    original = getattr(exc, "orig", None)
    return str(original) if original is not None else "restricao do banco violada"
