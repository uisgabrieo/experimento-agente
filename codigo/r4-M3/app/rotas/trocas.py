"""RF24 a RF29 - solicitacao e decisao de trocas de plantao."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, servicos
from app.db import obter_sessao
from app.paginacao import paginar
from app.schemas import EstadoTroca, Pagina, TrocaCriar, TrocaSaida

roteador = APIRouter(prefix="/trocas", tags=["trocas"])


@roteador.post("", response_model=TrocaSaida, status_code=status.HTTP_201_CREATED)
@roteador.post("/", response_model=TrocaSaida, status_code=status.HTTP_201_CREATED,
               include_in_schema=False)
def solicitar_troca(
    dados: TrocaCriar,
    sessao: Session = Depends(obter_sessao),
) -> models.Troca:
    """RF24 - cria a solicitacao em estado ``solicitada``."""

    origem = servicos.obter_plantao(sessao, dados.plantao_origem_id)
    destino = servicos.obter_plantao(sessao, dados.plantao_destino_id)
    troca = servicos.solicitar_troca(sessao, origem, destino)
    sessao.commit()
    sessao.refresh(troca)
    return troca


@roteador.get("", response_model=Pagina[TrocaSaida])
@roteador.get("/", response_model=Pagina[TrocaSaida], include_in_schema=False)
def listar_trocas(
    estado: EstadoTroca | None = Query(default=None),
    limite: int = Query(default=20, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    sessao: Session = Depends(obter_sessao),
) -> dict[str, object]:
    """RF29 - listagem, opcionalmente filtrada por estado."""

    filtros = []
    if estado is not None:
        filtros.append(models.Troca.estado == estado)

    consulta = select(models.Troca).where(*filtros).order_by(models.Troca.id)
    return paginar(sessao, consulta, limite=limite, deslocamento=deslocamento)


@roteador.get("/{troca_id}", response_model=TrocaSaida)
def consultar_troca(
    troca_id: int,
    sessao: Session = Depends(obter_sessao),
) -> models.Troca:
    """Consulta uma troca pelo identificador."""

    return servicos.obter_troca(sessao, troca_id)


@roteador.post("/{troca_id}/aprovacao", response_model=TrocaSaida, status_code=status.HTTP_200_OK)
def aprovar_troca(
    troca_id: int,
    sessao: Session = Depends(obter_sessao),
) -> models.Troca:
    """RF25/RF27 - aprova a troca de forma atomica."""

    troca = servicos.obter_troca(sessao, troca_id)
    servicos.aprovar_troca(sessao, troca)
    sessao.commit()
    sessao.refresh(troca)
    return troca


@roteador.post("/{troca_id}/rejeicao", response_model=TrocaSaida, status_code=status.HTTP_200_OK)
def rejeitar_troca(
    troca_id: int,
    sessao: Session = Depends(obter_sessao),
) -> models.Troca:
    """RF26/RF27 - rejeita a troca e registra a data da decisao."""

    troca = servicos.obter_troca(sessao, troca_id)
    servicos.rejeitar_troca(sessao, troca)
    sessao.commit()
    sessao.refresh(troca)
    return troca
