"""Roteadores HTTP da aplicacao."""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    ausencias,
    especialidades,
    plantoes,
    profissionais,
    saude,
    substituicoes,
    trocas,
    turnos,
)

ROTEADORES: tuple[APIRouter, ...] = (
    saude.router,
    profissionais.router,
    especialidades.router,
    turnos.router,
    plantoes.router,
    trocas.router,
    substituicoes.router,
    ausencias.router,
)

__all__ = ["ROTEADORES"]
