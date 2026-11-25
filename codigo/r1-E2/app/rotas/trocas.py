"""Rotas de trocas de plantao (RF24 a RF29)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from .. import constantes as C
from .. import repositorio, servicos
from ..banco import obter_sessao
from ..esquemas import Pagina, TrocaCriar, TrocaResposta
from ..modelos import Troca
from ..seguranca import exigir_coordenador

roteador = APIRouter(prefix="/trocas", tags=["trocas"])


@roteador.post(
    "",
    response_model=TrocaResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar troca",
)
def solicitar_troca(
    dados: TrocaCriar,
    sessao: Session = Depends(obter_sessao),
) -> Troca:
    """RF24 - cria a solicitacao em estado ``solicitada``."""

    origem = repositorio.obter_plantao(sessao, dados.plantao_origem_id)
    destino = repositorio.obter_plantao(sessao, dados.plantao_destino_id)
    return servicos.solicitar_troca(sessao, origem, destino)


@roteador.get("", response_model=Pagina[TrocaResposta], summary="Listar trocas")
def listar_trocas(
    sessao: Session = Depends(obter_sessao),
    estado: Literal["solicitada", "aprovada", "rejeitada"] | None = Query(None),
    limite: int = Query(C.LIMITE_PADRAO, ge=1, le=C.LIMITE_MAXIMO),
    deslocamento: int = Query(C.DESLOCAMENTO_PADRAO, ge=0),
) -> dict[str, object]:
    """RF29 - listagem no formato ``{itens, total}``, filtravel por estado."""

    itens, total = repositorio.listar_trocas(sessao, estado, limite, deslocamento)
    return {"itens": list(itens), "total": total}


@roteador.post(
    "/{troca_id}/aprovacao",
    response_model=TrocaResposta,
    status_code=status.HTTP_200_OK,
    summary="Aprovar troca",
    dependencies=[Depends(exigir_coordenador)],
)
def aprovar_troca(
    troca_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Troca:
    """RF25 - permuta atomica; qualquer violacao retorna 409 sem efeito."""

    troca = repositorio.obter_troca(sessao, troca_id)
    return servicos.aprovar_troca(sessao, troca)


@roteador.post(
    "/{troca_id}/rejeicao",
    response_model=TrocaResposta,
    status_code=status.HTTP_200_OK,
    summary="Rejeitar troca",
    dependencies=[Depends(exigir_coordenador)],
)
def rejeitar_troca(
    troca_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Troca:
    """RF26 - marca a troca como ``rejeitada`` e registra ``data_decisao``."""

    troca = repositorio.obter_troca(sessao, troca_id)
    return servicos.rejeitar_troca(sessao, troca)
