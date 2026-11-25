"""RF13 a RF22 - alocacao e cancelamento de plantoes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, servicos
from app.db import obter_sessao
from app.paginacao import paginar
from app.schemas import Pagina, PlantaoCriar, PlantaoSaida

roteador = APIRouter(prefix="/plantoes", tags=["plantoes"])


@roteador.post("", response_model=PlantaoSaida, status_code=status.HTTP_201_CREATED)
@roteador.post("/", response_model=PlantaoSaida, status_code=status.HTTP_201_CREATED,
               include_in_schema=False)
def criar_plantao(
    dados: PlantaoCriar,
    sessao: Session = Depends(obter_sessao),
) -> models.Plantao:
    """RF13 a RF21 - aloca o profissional no turno em estado confirmado."""

    turno = servicos.obter_turno(sessao, dados.turno_id)
    profissional = servicos.obter_profissional(sessao, dados.profissional_id)
    plantao = servicos.alocar_plantao(sessao, turno, profissional)
    sessao.commit()
    sessao.refresh(plantao)
    return plantao


@roteador.get("", response_model=Pagina[PlantaoSaida])
@roteador.get("/", response_model=Pagina[PlantaoSaida], include_in_schema=False)
def listar_plantoes(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    turno_id: int | None = Query(default=None, ge=1),
    profissional_id: int | None = Query(default=None, ge=1),
    estado: str | None = Query(default=None),
    limite: int = Query(default=20, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    sessao: Session = Depends(obter_sessao),
) -> dict[str, object]:
    """Listagem auxiliar de plantoes, com filtros simples."""

    filtros = []
    if turno_id is not None:
        filtros.append(models.Plantao.turno_id == turno_id)
    if profissional_id is not None:
        filtros.append(models.Plantao.profissional_id == profissional_id)
    if estado is not None:
        filtros.append(models.Plantao.estado == estado)

    consulta = select(models.Plantao).where(*filtros).order_by(models.Plantao.id)
    return paginar(sessao, consulta, limite=limite, deslocamento=deslocamento)


@roteador.get("/{plantao_id}", response_model=PlantaoSaida)
def consultar_plantao(
    plantao_id: int,
    sessao: Session = Depends(obter_sessao),
) -> models.Plantao:
    """Consulta um plantao pelo identificador."""

    return servicos.obter_plantao(sessao, plantao_id)


@roteador.delete("/{plantao_id}", response_model=PlantaoSaida, status_code=status.HTTP_200_OK)
def cancelar_plantao(
    plantao_id: int,
    sessao: Session = Depends(obter_sessao),
) -> models.Plantao:
    """RF22 - cancela o plantao, promove a fila e rejeita trocas pendentes."""

    plantao = servicos.obter_plantao(sessao, plantao_id)
    servicos.cancelar_plantao(sessao, plantao)
    sessao.commit()
    sessao.refresh(plantao)
    return plantao
