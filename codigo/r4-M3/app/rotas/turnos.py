"""RF09 a RF12 e RF36 - turnos e sua fila de substituicao."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, servicos
from app.db import obter_sessao
from app.paginacao import paginar
from app.schemas import (
    Pagina,
    SubstituicaoSaida,
    TurnoCriar,
    TurnoDetalhe,
    TurnoSaida,
)
from app.tempo import normalizar

roteador = APIRouter(prefix="/turnos", tags=["turnos"])


@roteador.post("", response_model=TurnoSaida, status_code=status.HTTP_201_CREATED)
@roteador.post("/", response_model=TurnoSaida, status_code=status.HTTP_201_CREATED,
               include_in_schema=False)
def criar_turno(
    dados: TurnoCriar,
    sessao: Session = Depends(obter_sessao),
) -> models.Turno:
    """RF09 - cadastra um turno; duracoes fora de 4h..12h resultam em 422."""

    servicos.obter_especialidade(sessao, dados.especialidade_id)

    turno = models.Turno(
        data_inicio=normalizar(dados.data_inicio),
        data_fim=normalizar(dados.data_fim),
        especialidade_id=dados.especialidade_id,
        cobertura_minima=dados.cobertura_minima,
    )
    sessao.add(turno)
    sessao.flush()
    sessao.commit()
    sessao.refresh(turno)
    return turno


@roteador.get("", response_model=Pagina[TurnoSaida])
@roteador.get("/", response_model=Pagina[TurnoSaida], include_in_schema=False)
def listar_turnos(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    de: datetime | None = Query(default=None),
    ate: datetime | None = Query(default=None),
    especialidade_id: int | None = Query(default=None, ge=1),
    limite: int = Query(default=20, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    sessao: Session = Depends(obter_sessao),
) -> dict[str, object]:
    """RF10 - listagem com os filtros temporais da secao 4.4."""

    filtros = []
    if de is not None:
        filtros.append(models.Turno.data_fim > normalizar(de))
    if ate is not None:
        filtros.append(models.Turno.data_inicio < normalizar(ate))
    if especialidade_id is not None:
        filtros.append(models.Turno.especialidade_id == especialidade_id)

    consulta = (
        select(models.Turno)
        .where(*filtros)
        .order_by(models.Turno.data_inicio, models.Turno.id)
    )
    return paginar(sessao, consulta, limite=limite, deslocamento=deslocamento)


@roteador.get("/{turno_id}", response_model=TurnoDetalhe)
def consultar_turno(
    turno_id: int,
    sessao: Session = Depends(obter_sessao),
) -> models.Turno:
    """RF11 - dados do turno acompanhados da lista de plantoes."""

    return servicos.obter_turno(sessao, turno_id)


@roteador.delete("/{turno_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_turno(
    turno_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Response:
    """RF12 - exclui o turno; 409 se houver plantao confirmado."""

    turno = servicos.obter_turno(sessao, turno_id)
    servicos.excluir_turno(sessao, turno)
    sessao.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@roteador.get("/{turno_id}/substituicoes", response_model=list[SubstituicaoSaida])
def consultar_fila(
    turno_id: int,
    sessao: Session = Depends(obter_sessao),
) -> list[models.Substituicao]:
    """RF36 - fila de substituicoes em espera, ordenada por posicao."""

    turno = servicos.obter_turno(sessao, turno_id)
    return servicos.fila_aguardando(sessao, turno.id)
