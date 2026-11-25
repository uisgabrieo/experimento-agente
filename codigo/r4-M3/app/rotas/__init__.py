"""Rotas HTTP da aplicacao, agrupadas por recurso."""

from app.rotas import (
    ausencias,
    especialidades,
    plantoes,
    profissionais,
    saude,
    substituicoes,
    trocas,
    turnos,
)

#: Ordem de registro dos roteadores em :mod:`app.main`.
ROTEADORES = (
    saude.roteador,
    profissionais.roteador,
    especialidades.roteador,
    turnos.roteador,
    plantoes.roteador,
    trocas.roteador,
    substituicoes.roteador,
    ausencias.roteador,
)

__all__ = ["ROTEADORES"]
