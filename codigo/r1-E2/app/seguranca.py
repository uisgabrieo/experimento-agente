"""Autenticacao por perfil, via cabecalho ``X-Auth-Key``.

As chaves validas vem das variaveis de ambiente ``CHAVE_COORDENADOR`` e
``CHAVE_PROFISSIONAL``, que identificam respectivamente os perfis
``coordenador`` e ``profissional``.

Se nenhuma das duas estiver definida, a autenticacao fica desativada e as
rotas mantem o comportamento anterior. Se pelo menos uma estiver definida,
a autenticacao fica ativa e somente as chaves correspondentes as variaveis
definidas sao aceitas: cabecalho ausente resulta em ``401`` e chave nao
reconhecida em ``403``.

A leitura das variaveis acontece a cada chamada para que o ambiente possa
ser ajustado sem reimportar a aplicacao.
"""

from __future__ import annotations

import os
from typing import Final

from fastapi import Depends, Header

from .erros import ErroDeNegocio

#: Cabecalho que transporta a chave de acesso.
CABECALHO_CHAVE: Final = "X-Auth-Key"

VAR_CHAVE_COORDENADOR: Final = "CHAVE_COORDENADOR"
VAR_CHAVE_PROFISSIONAL: Final = "CHAVE_PROFISSIONAL"

PERFIL_COORDENADOR: Final = "coordenador"
PERFIL_PROFISSIONAL: Final = "profissional"
#: Valor registrado na auditoria quando a autenticacao esta desativada.
PERFIL_DESATIVADA: Final = "desativada"
#: Valor registrado na auditoria quando a chave e ausente ou invalida.
PERFIL_DESCONHECIDO: Final = "desconhecido"


def _variavel(nome: str) -> str | None:
    """Valor da variavel de ambiente, tratando vazio como nao definida."""

    valor = os.getenv(nome)
    if valor is None or not valor.strip():
        return None
    return valor.strip()


def chaves_validas() -> dict[str, str]:
    """Mapa ``chave -> perfil`` com as chaves efetivamente configuradas.

    Dicionario vazio significa autenticacao desativada. Caso as duas
    variaveis tenham o mesmo valor, prevalece o perfil ``coordenador``.
    """

    mapa: dict[str, str] = {}
    chave_coordenador = _variavel(VAR_CHAVE_COORDENADOR)
    chave_profissional = _variavel(VAR_CHAVE_PROFISSIONAL)
    if chave_coordenador is not None:
        mapa[chave_coordenador] = PERFIL_COORDENADOR
    if chave_profissional is not None:
        mapa.setdefault(chave_profissional, PERFIL_PROFISSIONAL)
    return mapa


def autenticacao_ativa() -> bool:
    """Indica se pelo menos uma das variaveis de chave esta definida."""

    return bool(chaves_validas())


def perfil_para_auditoria(chave: str | None) -> str:
    """Perfil associado a chave, sem levantar erro.

    Usado pelo registro de auditoria, que precisa de um valor mesmo quando
    a requisicao e recusada com ``401`` ou ``403``.
    """

    mapa = chaves_validas()
    if not mapa:
        return PERFIL_DESATIVADA
    if chave is None:
        return PERFIL_DESCONHECIDO
    return mapa.get(chave, PERFIL_DESCONHECIDO)


def exigir_autenticacao(
    x_auth_key: str | None = Header(default=None, alias=CABECALHO_CHAVE),
) -> str:
    """Dependencia aplicada a todas as rotas, exceto ``GET /saude``.

    Retorna o perfil da requisicao (ou ``desativada``), levantando ``401``
    quando o cabecalho esta ausente e ``403`` quando a chave e invalida.
    """

    mapa = chaves_validas()
    if not mapa:
        return PERFIL_DESATIVADA
    if x_auth_key is None:
        raise ErroDeNegocio(401, f"cabecalho {CABECALHO_CHAVE} ausente")
    perfil = mapa.get(x_auth_key)
    if perfil is None:
        raise ErroDeNegocio(403, "chave de acesso nao reconhecida")
    return perfil


def exigir_coordenador(perfil: str = Depends(exigir_autenticacao)) -> str:
    """Dependencia das operacoes restritas ao perfil ``coordenador``.

    Com a autenticacao desativada a restricao nao se aplica, preservando o
    comportamento anterior das rotas.
    """

    if perfil in (PERFIL_DESATIVADA, PERFIL_COORDENADOR):
        return perfil
    raise ErroDeNegocio(403, "operacao restrita ao perfil coordenador")
