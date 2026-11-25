"""RF08 - cadastro de especialidades."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import func, select

from ..erros import Conflito
from ..models import Especialidade
from ..schemas import EspecialidadeCriar, EspecialidadeSaida, Pagina
from ..servicos import obter_especialidade
from .comum import Pag, Sessao, paginar

router = APIRouter(prefix="/especialidades", tags=["especialidades"])


@router.post(
    "",
    response_model=EspecialidadeSaida,
    status_code=status.HTTP_201_CREATED,
    summary="RF08 - criar especialidade",
)
def criar_especialidade(dados: EspecialidadeCriar, sessao: Sessao) -> Especialidade:
    """Cadastra uma especialidade; nome repetido resulta em 409."""

    existente = sessao.scalar(
        select(Especialidade.id).where(
            func.lower(Especialidade.nome) == dados.nome.lower()
        )
    )
    if existente is not None:
        raise Conflito(f"especialidade '{dados.nome}' ja cadastrada")

    especialidade = Especialidade(nome=dados.nome)
    sessao.add(especialidade)
    sessao.commit()
    return especialidade


@router.get("", response_model=Pagina[EspecialidadeSaida], summary="Listar especialidades")
def listar_especialidades(sessao: Sessao, pag: Pag) -> dict:
    """Lista as especialidades no envelope ``{itens, total}``."""

    return paginar(sessao, select(Especialidade), pag, Especialidade.id)


@router.get(
    "/{especialidade_id}",
    response_model=EspecialidadeSaida,
    summary="Consultar especialidade",
)
def consultar_especialidade(especialidade_id: int, sessao: Sessao) -> Especialidade:
    """Devolve uma especialidade pelo seu identificador."""

    return obter_especialidade(sessao, especialidade_id)
