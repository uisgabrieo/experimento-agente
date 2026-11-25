"""RF30 a RF34 - fila de substituicao."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from ..erros import Conflito
from ..estados import (
    SUBSTITUICAO_AGUARDANDO,
    SUBSTITUICAO_CANCELADA,
    SUBSTITUICAO_CONVOCADO,
)
from ..models import Substituicao
from ..regras import cobertura_atual, proxima_posicao, renumerar_fila
from ..schemas import AceiteSaida, SubstituicaoCriar, SubstituicaoSaida
from ..servicos import (
    aceitar_convocacao,
    obter_profissional,
    obter_substituicao,
    obter_turno,
)
from .comum import Sessao

router = APIRouter(prefix="/substituicoes", tags=["substituicoes"])


@router.post(
    "",
    response_model=SubstituicaoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="RF30 - entrar na fila de substituicao",
)
def entrar_na_fila(dados: SubstituicaoCriar, sessao: Sessao) -> Substituicao:
    turno = obter_turno(sessao, dados.turno_id)
    profissional = obter_profissional(sessao, dados.profissional_id)

    # RF32: sem a especialidade exigida, o profissional nao pode substituir.
    if not profissional.tem_especialidade(turno.especialidade_id):
        raise Conflito(
            f"profissional {profissional.id} nao possui a especialidade "
            f"{turno.especialidade_id} exigida pelo turno {turno.id}"
        )

    # RF31: a fila so existe enquanto houver necessidade de cobertura.
    cobertura = cobertura_atual(sessao, turno.id)
    if cobertura >= turno.cobertura_minima:
        raise Conflito(
            f"turno {turno.id} ja atende a cobertura minima "
            f"({cobertura}/{turno.cobertura_minima}); substituicao desnecessaria"
        )

    duplicada = sessao.scalar(
        select(Substituicao.id).where(
            Substituicao.turno_id == turno.id,
            Substituicao.profissional_id == profissional.id,
            Substituicao.estado.in_((SUBSTITUICAO_AGUARDANDO, SUBSTITUICAO_CONVOCADO)),
        )
    )
    if duplicada is not None:
        raise Conflito(
            f"profissional {profissional.id} ja esta na fila do turno {turno.id}"
        )

    substituicao = Substituicao(
        turno_id=turno.id,
        profissional_id=profissional.id,
        posicao=proxima_posicao(sessao, turno.id),
        estado=SUBSTITUICAO_AGUARDANDO,
    )
    sessao.add(substituicao)
    sessao.commit()
    return substituicao


@router.get(
    "/{substituicao_id}",
    response_model=SubstituicaoSaida,
    summary="Consultar substituicao",
)
def consultar_substituicao(substituicao_id: int, sessao: Sessao) -> Substituicao:
    return obter_substituicao(sessao, substituicao_id)


@router.delete(
    "/{substituicao_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="RF33 - sair da fila de substituicao",
)
def sair_da_fila(substituicao_id: int, sessao: Sessao) -> Response:
    substituicao = obter_substituicao(sessao, substituicao_id)

    if substituicao.estado != SUBSTITUICAO_AGUARDANDO:
        raise Conflito(
            f"substituicao {substituicao.id} nao esta aguardando "
            f"(estado atual: {substituicao.estado})"
        )

    turno_id = substituicao.turno_id
    substituicao.estado = SUBSTITUICAO_CANCELADA
    sessao.flush()
    # INV6: a fila restante volta a ser 1, 2, 3, ... sem lacunas.
    renumerar_fila(sessao, turno_id)
    sessao.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{substituicao_id}/aceite",
    response_model=AceiteSaida,
    status_code=status.HTTP_201_CREATED,
    summary="RF34 - aceitar convocacao",
)
def aceitar(substituicao_id: int, sessao: Sessao) -> dict:
    substituicao = obter_substituicao(sessao, substituicao_id)
    plantao, atendida = aceitar_convocacao(sessao, substituicao)
    sessao.commit()
    return {
        "id": plantao.id,
        "turno_id": plantao.turno_id,
        "profissional_id": plantao.profissional_id,
        "estado": plantao.estado,
        "substituicao": atendida,
    }
