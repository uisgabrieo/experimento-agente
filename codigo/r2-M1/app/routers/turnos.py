"""RF09 a RF12 e RF36 - turnos e sua fila de substituicoes."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import delete, or_, select

from ..erros import Conflito
from ..models import Troca, Turno
from ..regras import cobertura_atual, fila_aguardando
from ..schemas import Pagina, SubstituicaoSaida, TurnoCriar, TurnoDetalhe, TurnoSaida
from ..servicos import aplicar_filtro_temporal, obter_especialidade, obter_turno
from .comum import Intervalo, Pag, Sessao, paginar

router = APIRouter(prefix="/turnos", tags=["turnos"])


@router.post(
    "",
    response_model=TurnoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="RF09 - criar turno",
)
def criar_turno(dados: TurnoCriar, sessao: Sessao) -> Turno:
    """Cadastra um turno com duracao entre 4 e 12 horas (RF09)."""

    obter_especialidade(sessao, dados.especialidade_id)

    turno = Turno(
        data_inicio=dados.data_inicio,
        data_fim=dados.data_fim,
        especialidade_id=dados.especialidade_id,
        cobertura_minima=dados.cobertura_minima,
    )
    sessao.add(turno)
    sessao.commit()
    return turno


@router.get("", response_model=Pagina[TurnoSaida], summary="RF10 - listar turnos")
def listar_turnos(
    sessao: Sessao,
    pag: Pag,
    intervalo: Intervalo,
    especialidade_id: int | None = Query(None, ge=1),
) -> dict:
    """Lista turnos por especialidade e periodo ``[de, ate)`` (RF10)."""

    base = select(Turno)
    if especialidade_id is not None:
        base = base.where(Turno.especialidade_id == especialidade_id)
    base = aplicar_filtro_temporal(base, intervalo.de, intervalo.ate)
    return paginar(sessao, base, pag, Turno.data_inicio, Turno.id)


@router.get(
    "/{turno_id}",
    response_model=TurnoDetalhe,
    summary="RF11 - consultar turno com seus plantoes",
)
def consultar_turno(turno_id: int, sessao: Sessao) -> dict:
    """Devolve o turno com sua lista de plantoes (RF11)."""

    turno = obter_turno(sessao, turno_id)
    return {
        "id": turno.id,
        "data_inicio": turno.data_inicio,
        "data_fim": turno.data_fim,
        "especialidade_id": turno.especialidade_id,
        "cobertura_minima": turno.cobertura_minima,
        "plantoes": sorted(turno.plantoes, key=lambda p: p.id),
        "cobertura_atual": cobertura_atual(sessao, turno.id),
    }


@router.delete(
    "/{turno_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="RF12 - excluir turno",
)
def excluir_turno(turno_id: int, sessao: Sessao) -> Response:
    """Exclui o turno; plantao confirmado associado resulta em 409 (RF12)."""

    turno = obter_turno(sessao, turno_id)

    confirmados = cobertura_atual(sessao, turno.id)
    if confirmados:
        raise Conflito(
            f"turno {turno.id} possui {confirmados} plantao(oes) confirmado(s); "
            "cancele-os antes de excluir"
        )

    # Os plantoes cancelados do turno sairao em cascata; as trocas que os
    # referenciam precisam sair antes, para nao violar a chave estrangeira.
    ids_plantoes = [p.id for p in turno.plantoes]
    if ids_plantoes:
        sessao.execute(
            delete(Troca).where(
                or_(
                    Troca.plantao_origem_id.in_(ids_plantoes),
                    Troca.plantao_destino_id.in_(ids_plantoes),
                )
            )
        )

    sessao.delete(turno)
    sessao.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{turno_id}/substituicoes",
    response_model=list[SubstituicaoSaida],
    summary="RF36 - consultar fila de substituicao",
)
def consultar_fila(turno_id: int, sessao: Sessao) -> list:
    """Devolve a fila ``aguardando`` do turno ordenada por posicao (RF36)."""

    turno = obter_turno(sessao, turno_id)
    return fila_aguardando(sessao, turno.id)
