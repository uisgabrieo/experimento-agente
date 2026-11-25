"""Roteadores HTTP da aplicacao, agrupados por recurso.

Cada roteador e declarado junto das dependencias aplicadas a todas as suas
rotas. Todos exigem autenticacao, exceto ``GET /saude``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.params import Depends as Dependencia

from ..seguranca import exigir_autenticacao
from . import (
    auditoria,
    ausencias,
    especialidades,
    plantoes,
    profissionais,
    saude,
    substituicoes,
    trocas,
    turnos,
)

#: Dependencias comuns as rotas protegidas (401/403 conforme a chave).
AUTENTICADO: tuple[Dependencia, ...] = (Depends(exigir_autenticacao),)

#: Ordem de inclusao dos roteadores no aplicativo principal, com as
#: dependencias de cada um.
ROTEADORES: tuple[tuple[APIRouter, tuple[Dependencia, ...]], ...] = (
    (saude.roteador, ()),
    (profissionais.roteador, AUTENTICADO),
    (especialidades.roteador, AUTENTICADO),
    (turnos.roteador, AUTENTICADO),
    (plantoes.roteador, AUTENTICADO),
    (trocas.roteador, AUTENTICADO),
    (substituicoes.roteador, AUTENTICADO),
    (ausencias.roteador, AUTENTICADO),
    (auditoria.roteador, AUTENTICADO),
)

__all__ = ["AUTENTICADO", "ROTEADORES"]
