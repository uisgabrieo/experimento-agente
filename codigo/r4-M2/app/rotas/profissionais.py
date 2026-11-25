"""RF01 a RF07 e RF23 - cadastro, consulta e escala de profissionais."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, servicos
from app.db import obter_sessao
from app.erros import conflito
from app.paginacao import paginar
from app.schemas import (
    EscalaSaida,
    ItemEscalaSaida,
    Pagina,
    ProfissionalCriar,
    ProfissionalSaida,
    VinculoEspecialidade,
    VinculoSaida,
)
from app.tempo import duracao_segundos, horas, normalizar, recorta_periodo

roteador = APIRouter(prefix="/profissionais", tags=["profissionais"])


@roteador.post("", response_model=ProfissionalSaida, status_code=status.HTTP_201_CREATED)
@roteador.post("/", response_model=ProfissionalSaida, status_code=status.HTTP_201_CREATED,
               include_in_schema=False)
def criar_profissional(
    dados: ProfissionalCriar,
    sessao: Session = Depends(obter_sessao),
) -> models.Profissional:
    """RF01/RF02/RF03 - cadastra um profissional."""

    existente = sessao.execute(
        select(models.Profissional.id).where(models.Profissional.email == dados.email)
    ).first()
    if existente is not None:
        raise conflito("email ja cadastrado")

    profissional = models.Profissional(
        nome=dados.nome,
        email=dados.email,
        carga_semanal=dados.carga_semanal,
        ativo=dados.ativo,
        horas_extras=0,
    )
    sessao.add(profissional)
    sessao.flush()
    sessao.commit()
    sessao.refresh(profissional)
    return profissional


@roteador.get("", response_model=Pagina[ProfissionalSaida])
@roteador.get("/", response_model=Pagina[ProfissionalSaida], include_in_schema=False)
def listar_profissionais(
    limite: int = Query(default=20, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    sessao: Session = Depends(obter_sessao),
) -> dict[str, object]:
    """RF04 - listagem paginada."""

    consulta = select(models.Profissional).order_by(models.Profissional.id)
    return paginar(sessao, consulta, limite=limite, deslocamento=deslocamento)


@roteador.get("/{profissional_id}", response_model=ProfissionalSaida)
def consultar_profissional(
    profissional_id: int,
    sessao: Session = Depends(obter_sessao),
) -> models.Profissional:
    """RF05 - consulta por identificador."""

    return servicos.obter_profissional(sessao, profissional_id)


@roteador.post(
    "/{profissional_id}/especialidades",
    response_model=VinculoSaida,
    status_code=status.HTTP_201_CREATED,
)
def vincular_especialidade(
    profissional_id: int,
    dados: VinculoEspecialidade,
    sessao: Session = Depends(obter_sessao),
) -> dict[str, int]:
    """RF06 - vincula uma especialidade ao profissional."""

    profissional = servicos.obter_profissional(sessao, profissional_id)
    especialidade = servicos.obter_especialidade(sessao, dados.especialidade_id)
    servicos.vincular_especialidade(sessao, profissional, especialidade)
    sessao.commit()
    return {"profissional_id": profissional.id, "especialidade_id": especialidade.id}


@roteador.delete(
    "/{profissional_id}/especialidades/{esp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def desvincular_especialidade(
    profissional_id: int,
    esp_id: int,
    sessao: Session = Depends(obter_sessao),
) -> Response:
    """RF07 - remove o vinculo preservando INV4."""

    profissional = servicos.obter_profissional(sessao, profissional_id)
    especialidade = servicos.obter_especialidade(sessao, esp_id)
    servicos.desvincular_especialidade(sessao, profissional, especialidade)
    sessao.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@roteador.get("/{profissional_id}/escala", response_model=EscalaSaida)
def consultar_escala(
    profissional_id: int,
    de: datetime | None = Query(default=None),
    ate: datetime | None = Query(default=None),
    sessao: Session = Depends(obter_sessao),
) -> dict[str, object]:
    """RF23 - escala do profissional no periodo, seguindo a secao 4.4."""

    profissional = servicos.obter_profissional(sessao, profissional_id)
    limite_inicial = normalizar(de) if de is not None else None
    limite_final = normalizar(ate) if ate is not None else None

    consulta = (
        select(models.Plantao, models.Turno)
        .join(models.Turno, models.Turno.id == models.Plantao.turno_id)
        .where(
            models.Plantao.profissional_id == profissional.id,
            models.Plantao.estado == models.ESTADO_PLANTAO_CONFIRMADO,
        )
        .order_by(models.Turno.data_inicio, models.Plantao.id)
    )

    itens: list[ItemEscalaSaida] = []
    segundos_totais = 0
    for plantao, turno in sessao.execute(consulta).all():
        if not recorta_periodo(
            (turno.data_inicio, turno.data_fim), limite_inicial, limite_final
        ):
            continue
        segundos = duracao_segundos(turno.data_inicio, turno.data_fim)
        segundos_totais += segundos
        itens.append(
            ItemEscalaSaida.model_validate(
                {
                    "id": plantao.id,
                    "turno_id": turno.id,
                    "profissional_id": plantao.profissional_id,
                    "estado": plantao.estado,
                    "data_inicio": turno.data_inicio,
                    "data_fim": turno.data_fim,
                    "especialidade_id": turno.especialidade_id,
                    "horas": horas(segundos),
                }
            )
        )

    return {
        "itens": itens,
        "total": len(itens),
        "horas_periodo": horas(segundos_totais),
    }
