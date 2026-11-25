"""Rotas de turnos (RF09 a RF12 e RF36)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from .. import constantes as C
from .. import repositorio, servicos
from ..banco import obter_sessao
from ..esquemas import (
    Pagina,
    SubstituicaoResposta,
    TurnoCriar,
    TurnoDetalhe,
    TurnoResposta,
)
from ..modelos import Turno
from ..seguranca import exigir_coordenador
from ..tempo import para_naive_utc

roteador = APIRouter(prefix="/turnos", tags=["turnos"])


@roteador.post(
    "",
    response_model=TurnoResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Criar turno",
    dependencies=[Depends(exigir_coordenador)],
)
def criar_turno(
    dados: TurnoCriar,
    sessao: Session = Depends(obter_sessao),
) -> Turno:
    """RF09 - cadastra o turno; duracoes fora de 4h..12h resultam em 422."""

    repositorio.obter_especialidade(sessao, dados.especialidade_id)

    turno = Turno(
        data_inicio=para_naive_utc(dados.data_inicio),
        data_fim=para_naive_utc(dados.data_fim),
        especialidade_id=dados.especialidade_id,
        cobertura_minima=dados.cobertura_minima,
        noturno=dados.noturno,
    )
    sessao.add(turno)
    sessao.commit()
    return turno


@roteador.get("", response_model=Pagina[TurnoResposta], summary="Listar turnos")
def listar_turnos(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    sessao: Session = Depends(obter_sessao),
    de: datetime | None = Query(None, description="limite inicial inclusivo"),
    ate: datetime | None = Query(None, description="limite final exclusivo"),
    especialidade_id: int | None = Query(None, ge=1),
    noturno: bool | None = Query(None, description="filtra por turno noturno"),
    limite: int = Query(C.LIMITE_PADRAO, ge=1, le=C.LIMITE_MAXIMO),
    deslocamento: int = Query(C.DESLOCAMENTO_PADRAO, ge=0),
) -> dict[str, object]:
    """RF10 - listagem com os filtros temporais da secao 4.4.

    O filtro ``noturno`` e combinavel com os demais.
    """

    itens, total = repositorio.listar_turnos(
        sessao,
        para_naive_utc(de) if de is not None else None,
        para_naive_utc(ate) if ate is not None else None,
        especialidade_id,
        limite,
        deslocamento,
        noturno,
    )
    return {"itens": list(itens), "total": total}


@roteador.get(
    "/{turno_id}",
    response_model=TurnoDetalhe,
    summary="Consultar turno",
)
def consultar_turno(
    turno_id: int,
    sessao: Session = Depends(obter_sessao),
) -> dict[str, object]:
    """RF11 - dados do turno e sua lista de plantoes."""

    turno = repositorio.obter_turno(sessao, turno_id)
    plantoes = repositorio.plantoes_do_turno(sessao, turno_id)
    return {
        "id": turno.id,
        "data_inicio": turno.data_inicio,
        "data_fim": turno.data_fim,
        "especialidade_id": turno.especialidade_id,
        "cobertura_minima": turno.cobertura_minima,
        "noturno": turno.noturno,
        "plantoes": list(plantoes),
    }


@roteador.delete(
    "/{turno_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir turno",
    dependencies=[Depends(exigir_coordenador)],
)
def excluir_turno(
    turno_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Response:
    """RF12 - recusa a exclusao (409) quando houver plantao confirmado."""

    turno = repositorio.obter_turno(sessao, turno_id)
    servicos.excluir_turno(sessao, turno)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@roteador.get(
    "/{turno_id}/substituicoes",
    response_model=list[SubstituicaoResposta],
    summary="Consultar fila de substituicao do turno",
)
def consultar_fila(
    turno_id: int,
    sessao: Session = Depends(obter_sessao),
) -> list[object]:
    """RF36 - fila em estado ``aguardando`` ordenada por ``posicao``."""

    turno = repositorio.obter_turno(sessao, turno_id)
    return list(repositorio.fila_aguardando(sessao, turno.id))
