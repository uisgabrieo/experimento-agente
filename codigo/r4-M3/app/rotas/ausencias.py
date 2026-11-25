"""RF35 - registro de ausencias."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, servicos
from app.db import obter_sessao
from app.erros import nao_encontrado
from app.paginacao import paginar
from app.schemas import AusenciaCriar, AusenciaSaida, Pagina
from app.tempo import normalizar

roteador = APIRouter(prefix="/ausencias", tags=["ausencias"])


@roteador.post("", response_model=AusenciaSaida, status_code=status.HTTP_201_CREATED)
@roteador.post("/", response_model=AusenciaSaida, status_code=status.HTTP_201_CREATED,
               include_in_schema=False)
def criar_ausencia(
    dados: AusenciaCriar,
    sessao: Session = Depends(obter_sessao),
) -> models.Ausencia:
    """RF35 - registra a ausencia; 409 se houver plantao confirmado no periodo."""

    profissional = servicos.obter_profissional(sessao, dados.profissional_id)
    ausencia = servicos.registrar_ausencia(
        sessao,
        profissional,
        normalizar(dados.data_inicio),
        normalizar(dados.data_fim),
        dados.tipo,
    )
    sessao.commit()
    sessao.refresh(ausencia)
    return ausencia


@roteador.get("", response_model=Pagina[AusenciaSaida])
@roteador.get("/", response_model=Pagina[AusenciaSaida], include_in_schema=False)
def listar_ausencias(
    profissional_id: int | None = Query(default=None, ge=1),
    limite: int = Query(default=20, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    sessao: Session = Depends(obter_sessao),
) -> dict[str, object]:
    """Listagem auxiliar das ausencias registradas."""

    filtros = []
    if profissional_id is not None:
        filtros.append(models.Ausencia.profissional_id == profissional_id)

    consulta = (
        select(models.Ausencia)
        .where(*filtros)
        .order_by(models.Ausencia.data_inicio, models.Ausencia.id)
    )
    return paginar(sessao, consulta, limite=limite, deslocamento=deslocamento)


@roteador.get("/{ausencia_id}", response_model=AusenciaSaida)
def consultar_ausencia(
    ausencia_id: int,
    sessao: Session = Depends(obter_sessao),
) -> models.Ausencia:
    """Consulta uma ausencia pelo identificador."""

    ausencia = sessao.get(models.Ausencia, ausencia_id)
    if ausencia is None:
        raise nao_encontrado("ausencia nao encontrada")
    return ausencia
