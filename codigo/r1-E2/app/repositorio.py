"""Consultas reutilizadas pelas rotas e pelas regras de negocio.

Concentra o acesso ao banco para que as rotas permanecam enxutas e para que
as mesmas consultas sejam usadas tanto na validacao das invariantes quanto
na montagem das respostas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import count

from . import constantes as C
from .erros import nao_encontrado
from .modelos import (
    Ausencia,
    Especialidade,
    Plantao,
    Profissional,
    Substituicao,
    Troca,
    Turno,
)

E = TypeVar("E")


# --- Obtencao de entidades (404 quando inexistentes) ----------------------
def _obter(sessao: Session, modelo: type[E], rotulo: str, chave: int) -> E:
    """Retorna a entidade pelo identificador ou levanta ``404``."""
    entidade = sessao.get(modelo, chave)
    if entidade is None:
        raise nao_encontrado(rotulo, chave)
    return entidade


def obter_profissional(sessao: Session, profissional_id: int) -> Profissional:
    """Profissional existente ou ``404`` (RF05)."""
    return _obter(sessao, Profissional, "profissional", profissional_id)


def obter_especialidade(sessao: Session, especialidade_id: int) -> Especialidade:
    """Especialidade existente ou ``404``."""
    return _obter(sessao, Especialidade, "especialidade", especialidade_id)


def obter_turno(sessao: Session, turno_id: int) -> Turno:
    """Turno existente ou ``404`` (RF11)."""
    return _obter(sessao, Turno, "turno", turno_id)


def obter_plantao(sessao: Session, plantao_id: int) -> Plantao:
    """Plantao existente ou ``404``."""
    return _obter(sessao, Plantao, "plantao", plantao_id)


def obter_troca(sessao: Session, troca_id: int) -> Troca:
    """Troca existente ou ``404``."""
    return _obter(sessao, Troca, "troca", troca_id)


def obter_substituicao(sessao: Session, substituicao_id: int) -> Substituicao:
    """Substituicao existente ou ``404``."""
    return _obter(sessao, Substituicao, "substituicao", substituicao_id)


# --- Profissionais e especialidades ---------------------------------------
def buscar_profissional_por_email(sessao: Session, email: str) -> Profissional | None:
    """Profissional com o e-mail informado, ignorando caixa (RF03)."""
    return sessao.scalars(
        select(Profissional).where(func.lower(Profissional.email) == email.lower())
    ).first()


def buscar_especialidade_por_nome(sessao: Session, nome: str) -> Especialidade | None:
    """Especialidade com o nome informado, ignorando caixa (RF08)."""
    return sessao.scalars(
        select(Especialidade).where(func.lower(Especialidade.nome) == nome.lower())
    ).first()


def listar_profissionais(
    sessao: Session, limite: int, deslocamento: int
) -> tuple[Sequence[Profissional], int]:
    """Pagina de profissionais e o total de registros (RF04)."""
    total = sessao.scalar(select(count()).select_from(Profissional)) or 0
    itens = sessao.scalars(
        select(Profissional).order_by(Profissional.id).offset(deslocamento).limit(limite)
    ).all()
    return itens, int(total)


def turnos_que_exigem_especialidade(
    sessao: Session, profissional_id: int, especialidade_id: int
) -> Sequence[Turno]:
    """Turnos de uma especialidade com plantao confirmado do profissional."""
    return sessao.scalars(
        select(Turno)
        .join(Plantao, Plantao.turno_id == Turno.id)
        .where(
            Plantao.profissional_id == profissional_id,
            Plantao.estado == C.PLANTAO_CONFIRMADO,
            Turno.especialidade_id == especialidade_id,
        )
    ).all()


# --- Plantoes -------------------------------------------------------------
def plantoes_confirmados_do_profissional(
    sessao: Session, profissional_id: int
) -> Sequence[Plantao]:
    """Plantoes confirmados do profissional, ordenados pelo inicio do turno."""
    return sessao.scalars(
        select(Plantao)
        .join(Turno, Turno.id == Plantao.turno_id)
        .where(
            Plantao.profissional_id == profissional_id,
            Plantao.estado == C.PLANTAO_CONFIRMADO,
        )
        .order_by(Turno.data_inicio, Plantao.id)
    ).all()


def plantoes_do_turno(sessao: Session, turno_id: int) -> Sequence[Plantao]:
    """Todos os plantoes do turno, em qualquer estado, ordenados por id."""
    return sessao.scalars(
        select(Plantao).where(Plantao.turno_id == turno_id).order_by(Plantao.id)
    ).all()


def cobertura_atual(sessao: Session, turno_id: int) -> int:
    """Quantidade de plantoes confirmados associados ao turno."""
    total = sessao.scalar(
        select(count())
        .select_from(Plantao)
        .where(Plantao.turno_id == turno_id, Plantao.estado == C.PLANTAO_CONFIRMADO)
    )
    return int(total or 0)


def profissional_ja_alocado(
    sessao: Session, turno_id: int, profissional_id: int
) -> bool:
    """Indica se o profissional ja possui plantao confirmado no turno."""
    return (
        sessao.scalars(
            select(Plantao).where(
                Plantao.turno_id == turno_id,
                Plantao.profissional_id == profissional_id,
                Plantao.estado == C.PLANTAO_CONFIRMADO,
            )
        ).first()
        is not None
    )


# --- Ausencias e fila de substituicao -------------------------------------
def ausencias_do_profissional(
    sessao: Session, profissional_id: int
) -> Sequence[Ausencia]:
    """Ausencias do profissional, ordenadas pelo inicio do periodo (INV5)."""
    return sessao.scalars(
        select(Ausencia)
        .where(Ausencia.profissional_id == profissional_id)
        .order_by(Ausencia.data_inicio)
    ).all()


def fila_aguardando(sessao: Session, turno_id: int) -> Sequence[Substituicao]:
    """Fila de substituicoes em estado ``aguardando``, ordenada por posicao."""
    return sessao.scalars(
        select(Substituicao)
        .where(
            Substituicao.turno_id == turno_id,
            Substituicao.estado == C.SUB_AGUARDANDO,
        )
        .order_by(Substituicao.posicao, Substituicao.id)
    ).all()


# --- Trocas ---------------------------------------------------------------
def trocas_do_plantao(
    sessao: Session, plantao_id: int, estado: str | None = None
) -> Sequence[Troca]:
    """Trocas que envolvem o plantao, opcionalmente filtradas por estado."""
    consulta = select(Troca).where(
        (Troca.plantao_origem_id == plantao_id)
        | (Troca.plantao_destino_id == plantao_id)
    )
    if estado is not None:
        consulta = consulta.where(Troca.estado == estado)
    return sessao.scalars(consulta).all()


def listar_trocas(
    sessao: Session, estado: str | None, limite: int, deslocamento: int
) -> tuple[Sequence[Troca], int]:
    """Pagina de trocas, opcionalmente filtrada por estado (RF29)."""
    consulta = select(Troca)
    contagem = select(count()).select_from(Troca)
    if estado is not None:
        consulta = consulta.where(Troca.estado == estado)
        contagem = contagem.where(Troca.estado == estado)
    total = sessao.scalar(contagem) or 0
    itens = sessao.scalars(
        consulta.order_by(Troca.id).offset(deslocamento).limit(limite)
    ).all()
    return itens, int(total)


# --- Turnos ---------------------------------------------------------------
def listar_turnos(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    sessao: Session,
    de: datetime | None,
    ate: datetime | None,
    especialidade_id: int | None,
    limite: int,
    deslocamento: int,
    noturno: bool | None = None,
) -> tuple[Sequence[Turno], int]:
    """Lista turnos aplicando os filtros temporais da secao 4.4.

    O filtro ``noturno`` e opcional e combinavel com os demais (RF10).
    """
    consulta = select(Turno)
    contagem = select(count()).select_from(Turno)
    if de is not None:
        # Intervalos que terminem depois de `de` (limite inicial inclusivo).
        consulta = consulta.where(Turno.data_fim > de)
        contagem = contagem.where(Turno.data_fim > de)
    if ate is not None:
        # Intervalos que comecem antes de `ate` (limite final exclusivo).
        consulta = consulta.where(Turno.data_inicio < ate)
        contagem = contagem.where(Turno.data_inicio < ate)
    if especialidade_id is not None:
        consulta = consulta.where(Turno.especialidade_id == especialidade_id)
        contagem = contagem.where(Turno.especialidade_id == especialidade_id)
    if noturno is not None:
        consulta = consulta.where(Turno.noturno == noturno)
        contagem = contagem.where(Turno.noturno == noturno)

    total = sessao.scalar(contagem) or 0
    itens = sessao.scalars(
        consulta.order_by(Turno.data_inicio, Turno.id)
        .offset(deslocamento)
        .limit(limite)
    ).all()
    return itens, int(total)
