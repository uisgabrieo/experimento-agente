"""RF24 a RF29 - solicitacao, decisao e listagem de trocas."""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from ..erros import Conflito
from ..estados import ESTADOS_TROCA, PLANTAO_CONFIRMADO, TROCA_SOLICITADA
from ..models import Troca
from ..schemas import Pagina, TrocaCriar, TrocaSaida
from ..servicos import aprovar_troca, obter_plantao, obter_troca, rejeitar_troca
from .comum import Pag, Sessao, paginar, validar_opcao

router = APIRouter(prefix="/trocas", tags=["trocas"])


@router.post(
    "",
    response_model=TrocaSaida,
    status_code=status.HTTP_201_CREATED,
    summary="RF24 - solicitar troca",
)
def solicitar_troca(dados: TrocaCriar, sessao: Sessao) -> Troca:
    origem = obter_plantao(sessao, dados.plantao_origem_id)
    destino = obter_plantao(sessao, dados.plantao_destino_id)

    if origem.id == destino.id:
        raise Conflito("a troca exige dois plantoes distintos")

    for plantao in (origem, destino):
        if plantao.estado != PLANTAO_CONFIRMADO:
            raise Conflito(
                f"plantao {plantao.id} nao esta confirmado "
                f"(estado atual: {plantao.estado})"
            )

    if origem.profissional_id == destino.profissional_id:
        raise Conflito(
            "os plantoes da troca devem pertencer a profissionais diferentes"
        )

    troca = Troca(
        plantao_origem_id=origem.id,
        plantao_destino_id=destino.id,
        estado=TROCA_SOLICITADA,
        data_decisao=None,
    )
    sessao.add(troca)
    sessao.commit()
    return troca


@router.get("", response_model=Pagina[TrocaSaida], summary="RF29 - listar trocas")
def listar_trocas(sessao: Sessao, pag: Pag, estado: str | None = Query(None)) -> dict:
    base = select(Troca)
    if validar_opcao(estado, ESTADOS_TROCA, "estado") is not None:
        base = base.where(Troca.estado == estado)
    return paginar(sessao, base, pag, Troca.id)


@router.get("/{troca_id}", response_model=TrocaSaida, summary="Consultar troca")
def consultar_troca(troca_id: int, sessao: Sessao) -> Troca:
    return obter_troca(sessao, troca_id)


@router.post(
    "/{troca_id}/aprovacao",
    response_model=TrocaSaida,
    status_code=status.HTTP_200_OK,
    summary="RF25 - aprovar troca",
)
def aprovar(troca_id: int, sessao: Sessao) -> Troca:
    troca = aprovar_troca(sessao, obter_troca(sessao, troca_id))
    sessao.commit()
    return troca


@router.post(
    "/{troca_id}/rejeicao",
    response_model=TrocaSaida,
    status_code=status.HTTP_200_OK,
    summary="RF26 - rejeitar troca",
)
def rejeitar(troca_id: int, sessao: Sessao) -> Troca:
    troca = rejeitar_troca(sessao, obter_troca(sessao, troca_id))
    sessao.commit()
    return troca
