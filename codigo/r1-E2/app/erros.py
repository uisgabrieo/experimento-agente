"""Erros de dominio.

Toda resposta 4xx da aplicacao carrega a chave ``detail`` (RF37). As
excecoes abaixo sao convertidas em respostas JSON pelo manipulador
registrado em :mod:`app.main`.
"""

from __future__ import annotations


class ErroDeNegocio(Exception):
    """Erro de dominio com codigo HTTP e mensagem associados."""

    def __init__(self, status: int, detalhe: str) -> None:
        super().__init__(detalhe)
        self.status = status
        self.detalhe = detalhe


class NaoEncontrado(ErroDeNegocio):
    """Recurso inexistente (404)."""

    def __init__(self, detalhe: str) -> None:
        super().__init__(404, detalhe)


class Conflito(ErroDeNegocio):
    """Operacao que violaria uma regra de negocio ou invariante (409)."""

    def __init__(self, detalhe: str) -> None:
        super().__init__(409, detalhe)


class DadosInvalidos(ErroDeNegocio):
    """Dados que nao satisfazem as regras da secao 3 (422)."""

    def __init__(self, detalhe: str) -> None:
        super().__init__(422, detalhe)


def nao_encontrado(recurso: str, identificador: object) -> NaoEncontrado:
    """Constroi um erro 404 padronizado."""

    return NaoEncontrado(f"{recurso} {identificador} nao encontrado")
