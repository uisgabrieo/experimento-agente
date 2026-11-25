"""RF30 a RF34 - fila de substituicao."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, servicos
from app.db import obter_sessao
from app.paginacao import paginar
from app.schemas import (
    EstadoSubstituicao,
    Pagina,
    PlantaoSaida,
    SubstituicaoCriar,
    SubstituicaoSaida,
)

roteador = APIRouter(prefix="/substituicoes", tags=["substituicoes"])


@roteador.post("", response_model=SubstituicaoSaida, status_code=status.HTTP_201_CREATED)
@roteador.post("/", response_model=SubstituicaoSaida, status_code=status.HTTP_201_CREATED,
               include_in_schema=False)
def entrar_na_fila(
    dados: SubstituicaoCriar,
    sessao: Session = Depends(obter_sessao),
) -> models.Substituicao:
    """RF30/RF31/RF32 - inscreve o profissional na fila do turno."""

    turno = servicos.obter_turno(sessao, dados.turno_id)
    profissional = servicos.obter_profissional(sessao, dados.profissional_id)
    substituicao = servicos.entrar_na_fila(sessao, turno, profissional)
    sessao.commit()
    sessao.refresh(substituicao)
    return substituicao


@roteador.get("", response_model=Pagina[SubstituicaoSaida])
@roteador.get("/", response_model=Pagina[SubstituicaoSaida], include_in_schema=False)
def listar_substituicoes(
    turno_id: int | None = Query(default=None, ge=1),
    estado: EstadoSubstituicao | None = Query(default=None),
    limite: int = Query(default=20, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    sessao: Session = Depends(obter_sessao),
) -> dict[str, object]:
    """Listagem auxiliar das substituicoes registradas."""

    filtros = []
    if turno_id is not None:
        filtros.append(models.Substituicao.turno_id == turno_id)
    if estado is not None:
        filtros.append(models.Substituicao.estado == estado)

    consulta = (
        select(models.Substituicao)
        .where(*filtros)
        .order_by(models.Substituicao.turno_id, models.Substituicao.posicao)
    )
    return paginar(sessao, consulta, limite=limite, deslocamento=deslocamento)


@roteador.get("/{substituicao_id}", response_model=SubstituicaoSaida)
def consultar_substituicao(
    substituicao_id: int,
    sessao: Session = Depends(obter_sessao),
) -> models.Substituicao:
    """Consulta uma substituicao pelo identificador."""

    return servicos.obter_substituicao(sessao, substituicao_id)


@roteador.delete("/{substituicao_id}", status_code=status.HTTP_204_NO_CONTENT)
def sair_da_fila(
    substituicao_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Response:
    """RF33 - cancela a inscricao e reorganiza a fila, preservando INV6."""

    substituicao = servicos.obter_substituicao(sessao, substituicao_id)
    servicos.sair_da_fila(sessao, substituicao)
    sessao.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@roteador.post(
    "/{substituicao_id}/aceite",
    response_model=PlantaoSaida,
    status_code=status.HTTP_201_CREATED,
)
def aceitar_convocacao(
    substituicao_id: int,
    sessao: Session = Depends(obter_sessao),
) -> models.Plantao:
    """RF34 - converte a convocacao em plantao confirmado."""

    substituicao = servicos.obter_substituicao(sessao, substituicao_id)
    plantao = servicos.aceitar_convocacao(sessao, substituicao)
    sessao.commit()
    sessao.refresh(plantao)
    return plantao
