"""Rotas de profissionais (RF01 a RF07 e RF23)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from .. import constantes as C
from .. import repositorio, servicos
from ..banco import obter_sessao
from ..erros import Conflito
from ..esquemas import (
    EscalaResposta,
    Pagina,
    ProfissionalCriar,
    ProfissionalResposta,
    VinculoEspecialidade,
)
from ..modelos import Profissional
from ..seguranca import exigir_coordenador
from ..tempo import (
    dentro_do_periodo,
    duracao_horas,
    horas_recortadas,
    para_naive_utc,
)

roteador = APIRouter(prefix="/profissionais", tags=["profissionais"])


@roteador.post(
    "",
    response_model=ProfissionalResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Criar profissional",
    dependencies=[Depends(exigir_coordenador)],
)
def criar_profissional(
    dados: ProfissionalCriar,
    sessao: Session = Depends(obter_sessao),
) -> Profissional:
    """RF01 - cadastra um profissional.

    RF02 trata as validacoes sintaticas (422, via Pydantic) e RF03 o
    conflito de e-mail duplicado (409).
    """

    if repositorio.buscar_profissional_por_email(sessao, dados.email) is not None:
        raise Conflito(f"o e-mail '{dados.email}' ja esta cadastrado")

    profissional = Profissional(
        nome=dados.nome,
        email=dados.email,
        carga_semanal=dados.carga_semanal,
        ativo=dados.ativo,
        horas_extras=0,
    )
    sessao.add(profissional)
    sessao.commit()
    return profissional


@roteador.get(
    "",
    response_model=Pagina[ProfissionalResposta],
    summary="Listar profissionais",
)
def listar_profissionais(
    sessao: Session = Depends(obter_sessao),
    limite: int = Query(C.LIMITE_PADRAO, ge=1, le=C.LIMITE_MAXIMO),
    deslocamento: int = Query(C.DESLOCAMENTO_PADRAO, ge=0),
) -> dict[str, object]:
    """RF04 - listagem paginada no formato ``{itens, total}``."""

    itens, total = repositorio.listar_profissionais(sessao, limite, deslocamento)
    return {"itens": list(itens), "total": total}


@roteador.get(
    "/{profissional_id}",
    response_model=ProfissionalResposta,
    summary="Consultar profissional",
)
def consultar_profissional(
    profissional_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Profissional:
    """RF05 - 200 quando existir, 404 caso contrario."""

    return repositorio.obter_profissional(sessao, profissional_id)


@roteador.post(
    "/{profissional_id}/especialidades",
    response_model=ProfissionalResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Vincular especialidade ao profissional",
)
def vincular_especialidade(
    profissional_id: int,
    dados: VinculoEspecialidade,
    sessao: Session = Depends(obter_sessao),
) -> Profissional:
    """RF06 - vincula a especialidade; vinculo repetido resulta em 409."""

    profissional = repositorio.obter_profissional(sessao, profissional_id)
    especialidade = repositorio.obter_especialidade(sessao, dados.especialidade_id)
    return servicos.vincular_especialidade(sessao, profissional, especialidade)


@roteador.delete(
    "/{profissional_id}/especialidades/{esp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover especialidade do profissional",
)
def remover_especialidade(
    profissional_id: int,
    esp_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Response:
    """RF07 - remove o vinculo preservando INV4 (409 quando houver plantao)."""

    profissional = repositorio.obter_profissional(sessao, profissional_id)
    servicos.desvincular_especialidade(sessao, profissional, esp_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@roteador.get(
    "/{profissional_id}/escala",
    response_model=EscalaResposta,
    summary="Consultar escala do profissional",
)
def consultar_escala(
    profissional_id: int,
    sessao: Session = Depends(obter_sessao),
    de: datetime | None = Query(None, description="limite inicial inclusivo"),
    ate: datetime | None = Query(None, description="limite final exclusivo"),
) -> dict[str, object]:
    """RF23 - plantoes confirmados do profissional no periodo ``[de, ate)``."""

    profissional = repositorio.obter_profissional(sessao, profissional_id)

    inicio = para_naive_utc(de) if de is not None else None
    fim = para_naive_utc(ate) if ate is not None else None

    itens: list[dict[str, object]] = []
    horas_periodo = 0.0

    for plantao in repositorio.plantoes_confirmados_do_profissional(
        sessao, profissional.id
    ):
        turno = plantao.turno
        if not dentro_do_periodo(turno.data_inicio, turno.data_fim, inicio, fim):
            continue
        # Turnos noturnos recebem adicional de 20% apenas em `horas_periodo`;
        # `horas_extras` e INV3 seguem usando a duracao real do plantao.
        fator = C.ADICIONAL_NOTURNO if turno.noturno else 1.0
        horas_periodo += (
            horas_recortadas(turno.data_inicio, turno.data_fim, inicio, fim) * fator
        )
        itens.append(
            {
                "id": plantao.id,
                "turno_id": plantao.turno_id,
                "profissional_id": plantao.profissional_id,
                "estado": plantao.estado,
                "data_inicio": turno.data_inicio,
                "data_fim": turno.data_fim,
                "especialidade_id": turno.especialidade_id,
                "horas": round(
                    duracao_horas(turno.data_inicio, turno.data_fim), 2
                ),
            }
        )

    return {
        "itens": itens,
        "total": len(itens),
        "horas_periodo": round(horas_periodo, 2),
    }
