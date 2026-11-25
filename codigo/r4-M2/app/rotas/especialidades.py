"""RF08 - cadastro de especialidades."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, servicos
from app.db import obter_sessao
from app.erros import conflito
from app.paginacao import paginar
from app.schemas import EspecialidadeCriar, EspecialidadeSaida, Pagina

roteador = APIRouter(prefix="/especialidades", tags=["especialidades"])


@roteador.post("", response_model=EspecialidadeSaida, status_code=status.HTTP_201_CREATED)
@roteador.post("/", response_model=EspecialidadeSaida, status_code=status.HTTP_201_CREATED,
               include_in_schema=False)
def criar_especialidade(
    dados: EspecialidadeCriar,
    sessao: Session = Depends(obter_sessao),
) -> models.Especialidade:
    """RF08 - cadastra uma especialidade; nome duplicado resulta em 409."""

    existente = sessao.execute(
        select(models.Especialidade.id).where(models.Especialidade.nome == dados.nome)
    ).first()
    if existente is not None:
        raise conflito("especialidade ja cadastrada")

    especialidade = models.Especialidade(nome=dados.nome)
    sessao.add(especialidade)
    sessao.flush()
    sessao.commit()
    sessao.refresh(especialidade)
    return especialidade


@roteador.get("", response_model=Pagina[EspecialidadeSaida])
@roteador.get("/", response_model=Pagina[EspecialidadeSaida], include_in_schema=False)
def listar_especialidades(
    limite: int = Query(default=20, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    sessao: Session = Depends(obter_sessao),
) -> dict[str, object]:
    """Listagem paginada de especialidades."""

    consulta = select(models.Especialidade).order_by(models.Especialidade.id)
    return paginar(sessao, consulta, limite=limite, deslocamento=deslocamento)


@roteador.get("/{especialidade_id}", response_model=EspecialidadeSaida)
def consultar_especialidade(
    especialidade_id: int,
    sessao: Session = Depends(obter_sessao),
) -> models.Especialidade:
    """Consulta uma especialidade pelo identificador."""

    return servicos.obter_especialidade(sessao, especialidade_id)
