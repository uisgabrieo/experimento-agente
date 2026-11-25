"""RF01 a RF07 e RF23 - cadastro, consulta e escala dos profissionais."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from ..erros import Conflito
from ..models import Profissional, profissional_especialidade
from ..regras import conflitos_de_especialidade
from ..schemas import (
    EscalaSaida,
    Pagina,
    ProfissionalCriar,
    ProfissionalSaida,
    VinculoEspecialidade,
)
from ..servicos import (
    escala_do_profissional,
    obter_especialidade,
    obter_profissional,
)
from .comum import Intervalo, Pag, Sessao, paginar

router = APIRouter(prefix="/profissionais", tags=["profissionais"])


def _email_em_uso(sessao: Session, email: str) -> bool:
    return (
        sessao.scalar(
            select(Profissional.id).where(
                func.lower(Profissional.email) == email.lower()
            )
        )
        is not None
    )


@router.post(
    "",
    response_model=ProfissionalSaida,
    status_code=status.HTTP_201_CREATED,
    summary="RF01 - criar profissional",
)
def criar_profissional(dados: ProfissionalCriar, sessao: Sessao) -> Profissional:
    """Cadastra um profissional; email repetido resulta em 409 (RF03)."""

    if _email_em_uso(sessao, dados.email):
        raise Conflito(f"email '{dados.email}' ja cadastrado")

    profissional = Profissional(
        nome=dados.nome,
        email=dados.email,
        carga_semanal=dados.carga_semanal,
        ativo=dados.ativo,
        horas_extras=0.0,
    )
    sessao.add(profissional)
    sessao.commit()
    return profissional


@router.get(
    "",
    response_model=Pagina[ProfissionalSaida],
    summary="RF04 - listar profissionais",
)
def listar_profissionais(sessao: Sessao, pag: Pag) -> dict:
    """Lista os profissionais no envelope ``{itens, total}``."""

    return paginar(sessao, select(Profissional), pag, Profissional.id)


@router.get(
    "/{profissional_id}",
    response_model=ProfissionalSaida,
    summary="RF05 - consultar profissional",
)
def consultar_profissional(profissional_id: int, sessao: Sessao) -> Profissional:
    """Devolve um profissional pelo seu identificador."""

    return obter_profissional(sessao, profissional_id)


@router.post(
    "/{profissional_id}/especialidades",
    response_model=ProfissionalSaida,
    status_code=status.HTTP_201_CREATED,
    summary="RF06 - vincular especialidade",
)
def vincular_especialidade(
    profissional_id: int, dados: VinculoEspecialidade, sessao: Sessao
) -> Profissional:
    """Vincula uma especialidade; vinculo existente resulta em 409."""

    profissional = obter_profissional(sessao, profissional_id)
    especialidade = obter_especialidade(sessao, dados.especialidade_id)

    if profissional.tem_especialidade(especialidade.id):
        raise Conflito(
            f"profissional {profissional.id} ja possui a especialidade "
            f"{especialidade.id}"
        )

    sessao.execute(
        insert(profissional_especialidade).values(
            profissional_id=profissional.id, especialidade_id=especialidade.id
        )
    )
    sessao.commit()
    return profissional


@router.delete(
    "/{profissional_id}/especialidades/{especialidade_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="RF07 - remover especialidade",
)
def remover_especialidade(
    profissional_id: int, especialidade_id: int, sessao: Sessao
) -> Response:
    """Remove o vinculo de especialidade, preservando INV4."""

    profissional = obter_profissional(sessao, profissional_id)

    # Preserva INV4: o vinculo sustenta plantoes confirmados existentes.
    pendentes = conflitos_de_especialidade(sessao, profissional.id, especialidade_id)
    if pendentes:
        raise Conflito(
            f"INV4: existem {pendentes} plantao(oes) confirmado(s) em turnos que "
            f"exigem a especialidade {especialidade_id}; cancele-os antes de "
            "remover o vinculo"
        )

    sessao.execute(
        delete(profissional_especialidade).where(
            profissional_especialidade.c.profissional_id == profissional.id,
            profissional_especialidade.c.especialidade_id == especialidade_id,
        )
    )
    sessao.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{profissional_id}/escala",
    response_model=EscalaSaida,
    summary="RF23 - consultar escala do profissional",
)
def consultar_escala(
    profissional_id: int, sessao: Sessao, intervalo: Intervalo
) -> dict:
    """Devolve a escala do profissional no periodo ``[de, ate)`` (RF23)."""

    profissional = obter_profissional(sessao, profissional_id)
    itens, horas = escala_do_profissional(
        sessao, profissional, intervalo.de, intervalo.ate
    )
    return {"itens": itens, "total": len(itens), "horas_periodo": horas}
