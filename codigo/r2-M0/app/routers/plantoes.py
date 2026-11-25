"""RF13 a RF22 - alocacao e cancelamento de plantoes."""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from ..estados import ESTADOS_PLANTAO
from ..models import Plantao
from ..schemas import Pagina, PlantaoCriar, PlantaoSaida
from ..servicos import (
    cancelar_plantao,
    criar_plantao,
    obter_plantao,
    obter_profissional,
    obter_turno,
)
from .comum import Pag, Sessao, paginar, validar_opcao

router = APIRouter(prefix="/plantoes", tags=["plantoes"])


@router.post(
    "",
    response_model=PlantaoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="RF13 - alocar profissional em turno",
)
def alocar(dados: PlantaoCriar, sessao: Sessao) -> Plantao:
    turno = obter_turno(sessao, dados.turno_id)
    profissional = obter_profissional(sessao, dados.profissional_id)

    plantao = criar_plantao(sessao, turno, profissional)
    sessao.commit()
    return plantao


@router.get("", response_model=Pagina[PlantaoSaida], summary="Listar plantoes")
def listar_plantoes(
    sessao: Sessao,
    pag: Pag,
    turno_id: int | None = Query(None, ge=1),
    profissional_id: int | None = Query(None, ge=1),
    estado: str | None = Query(None),
) -> dict:
    base = select(Plantao)
    if turno_id is not None:
        base = base.where(Plantao.turno_id == turno_id)
    if profissional_id is not None:
        base = base.where(Plantao.profissional_id == profissional_id)
    if validar_opcao(estado, ESTADOS_PLANTAO, "estado") is not None:
        base = base.where(Plantao.estado == estado)
    return paginar(sessao, base, pag, Plantao.id)


@router.get("/{plantao_id}", response_model=PlantaoSaida, summary="Consultar plantao")
def consultar_plantao(plantao_id: int, sessao: Sessao) -> Plantao:
    return obter_plantao(sessao, plantao_id)


@router.delete(
    "/{plantao_id}",
    response_model=PlantaoSaida,
    status_code=status.HTTP_200_OK,
    summary="RF22 - cancelar plantao",
)
def cancelar(plantao_id: int, sessao: Sessao) -> Plantao:
    plantao = obter_plantao(sessao, plantao_id)
    cancelar_plantao(sessao, plantao)
    sessao.commit()
    return plantao
