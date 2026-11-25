"""Rotas da fila de substituicao (RF30 a RF34)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from .. import repositorio, servicos
from ..banco import obter_sessao
from ..esquemas import PlantaoResposta, SubstituicaoCriar, SubstituicaoResposta
from ..modelos import Plantao, Substituicao

roteador = APIRouter(prefix="/substituicoes", tags=["substituicoes"])


@roteador.post(
    "",
    response_model=SubstituicaoResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Entrar na fila de substituicao",
)
def entrar_na_fila(
    dados: SubstituicaoCriar,
    sessao: Session = Depends(obter_sessao),
) -> Substituicao:
    """RF30 - cria a substituicao em estado ``aguardando``.

    A posicao atribuida e a ultima existente acrescida de 1 (INV6). RF31 e
    RF32 recusam a inscricao com 409.
    """

    turno = repositorio.obter_turno(sessao, dados.turno_id)
    profissional = repositorio.obter_profissional(sessao, dados.profissional_id)
    return servicos.inscrever_substituicao(sessao, turno, profissional)


@roteador.get(
    "/{substituicao_id}",
    response_model=SubstituicaoResposta,
    summary="Consultar substituicao",
)
def consultar_substituicao(
    substituicao_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Substituicao:
    """Dados da substituicao; ``404`` quando nao encontrada."""

    return repositorio.obter_substituicao(sessao, substituicao_id)


@roteador.delete(
    "/{substituicao_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sair da fila de substituicao",
)
def sair_da_fila(
    substituicao_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Response:
    """RF33 - cancela a substituicao e reindexa a fila (INV6)."""

    substituicao = repositorio.obter_substituicao(sessao, substituicao_id)
    servicos.cancelar_substituicao(sessao, substituicao)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@roteador.post(
    "/{substituicao_id}/aceite",
    response_model=PlantaoResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Aceitar convocacao",
)
def aceitar_convocacao(
    substituicao_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Plantao:
    """RF34 - cria o plantao e marca a substituicao como ``atendida``."""

    substituicao = repositorio.obter_substituicao(sessao, substituicao_id)
    return servicos.aceitar_convocacao(sessao, substituicao)
