"""Rotas de ausencias (RF35)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from .. import repositorio, servicos
from ..banco import obter_sessao
from ..erros import nao_encontrado
from ..esquemas import AusenciaCriar, AusenciaResposta
from ..modelos import Ausencia
from ..tempo import para_naive_utc

roteador = APIRouter(prefix="/ausencias", tags=["ausencias"])


@roteador.post(
    "",
    response_model=AusenciaResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar ausencia",
)
def registrar_ausencia(
    dados: AusenciaCriar,
    sessao: Session = Depends(obter_sessao),
) -> Ausencia:
    """RF35 - registra a ausencia; plantao confirmado sobreposto gera 409."""

    profissional = repositorio.obter_profissional(sessao, dados.profissional_id)
    return servicos.registrar_ausencia(
        sessao,
        profissional,
        para_naive_utc(dados.data_inicio),
        para_naive_utc(dados.data_fim),
        dados.tipo,
    )


@roteador.get(
    "/{ausencia_id}",
    response_model=AusenciaResposta,
    summary="Consultar ausencia",
)
def consultar_ausencia(
    ausencia_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Ausencia:
    """Dados da ausencia; ``404`` quando nao encontrada."""

    ausencia = sessao.get(Ausencia, ausencia_id)
    if ausencia is None:
        raise nao_encontrado("ausencia", ausencia_id)
    return ausencia
