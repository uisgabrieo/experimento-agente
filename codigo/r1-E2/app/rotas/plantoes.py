"""Rotas de plantoes (RF13 a RF22)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from .. import repositorio, servicos
from ..banco import obter_sessao
from ..esquemas import PlantaoCriar, PlantaoResposta
from ..modelos import Plantao

roteador = APIRouter(prefix="/plantoes", tags=["plantoes"])


@roteador.post(
    "",
    response_model=PlantaoResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Alocar profissional em turno",
)
def alocar_plantao(
    dados: PlantaoCriar,
    sessao: Session = Depends(obter_sessao),
) -> Plantao:
    """RF13 - cria o plantao em estado ``confirmado``.

    As recusas previstas em RF14 a RF21 retornam 409 com o motivo em
    ``detail``.
    """

    turno = repositorio.obter_turno(sessao, dados.turno_id)
    profissional = repositorio.obter_profissional(sessao, dados.profissional_id)
    return servicos.alocar_plantao(sessao, turno, profissional)


@roteador.get(
    "/{plantao_id}",
    response_model=PlantaoResposta,
    summary="Consultar plantao",
)
def consultar_plantao(
    plantao_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Plantao:
    """Dados do plantao; ``404`` quando nao encontrado."""

    return repositorio.obter_plantao(sessao, plantao_id)


@roteador.delete(
    "/{plantao_id}",
    response_model=PlantaoResposta,
    status_code=status.HTTP_200_OK,
    summary="Cancelar plantao",
)
def cancelar_plantao(
    plantao_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Plantao:
    """RF22 - cancela o plantao e aciona a fila de substituicao."""

    plantao = repositorio.obter_plantao(sessao, plantao_id)
    return servicos.cancelar_plantao(sessao, plantao)
