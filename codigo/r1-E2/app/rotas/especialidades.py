"""Rotas de especialidades (RF08)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from .. import repositorio
from ..banco import obter_sessao
from ..erros import Conflito
from ..esquemas import EspecialidadeCriar, EspecialidadeResposta
from ..modelos import Especialidade

roteador = APIRouter(prefix="/especialidades", tags=["especialidades"])


@roteador.post(
    "",
    response_model=EspecialidadeResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Criar especialidade",
)
def criar_especialidade(
    dados: EspecialidadeCriar,
    sessao: Session = Depends(obter_sessao),
) -> Especialidade:
    """RF08 - cadastra uma especialidade; nome repetido resulta em 409."""

    if repositorio.buscar_especialidade_por_nome(sessao, dados.nome) is not None:
        raise Conflito(f"a especialidade '{dados.nome}' ja esta cadastrada")

    especialidade = Especialidade(nome=dados.nome)
    sessao.add(especialidade)
    sessao.commit()
    return especialidade


@roteador.get(
    "/{especialidade_id}",
    response_model=EspecialidadeResposta,
    summary="Consultar especialidade",
)
def consultar_especialidade(
    especialidade_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Especialidade:
    """Dados da especialidade; ``404`` quando nao encontrada."""

    return repositorio.obter_especialidade(sessao, especialidade_id)
