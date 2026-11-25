"""Modelos ORM.

Os nomes de tabelas e colunas exigidos pela secao 2.1 da especificacao fazem
parte do contrato e sao mantidos exatamente como descritos.
"""

# Modelos declarativos expoem estado, nao comportamento: a contagem minima de
# metodos publicos nao se aplica a eles.
# pylint: disable=too-few-public-methods

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# ---------------------------------------------------------------------------
# Estados e tipos aceitos
# ---------------------------------------------------------------------------

ESTADO_PLANTAO_CONFIRMADO = "confirmado"
ESTADO_PLANTAO_CANCELADO = "cancelado"
ESTADOS_PLANTAO = (ESTADO_PLANTAO_CONFIRMADO, ESTADO_PLANTAO_CANCELADO)

ESTADO_TROCA_SOLICITADA = "solicitada"
ESTADO_TROCA_APROVADA = "aprovada"
ESTADO_TROCA_REJEITADA = "rejeitada"
ESTADOS_TROCA = (ESTADO_TROCA_SOLICITADA, ESTADO_TROCA_APROVADA, ESTADO_TROCA_REJEITADA)

ESTADO_SUB_AGUARDANDO = "aguardando"
ESTADO_SUB_CONVOCADO = "convocado"
ESTADO_SUB_ATENDIDA = "atendida"
ESTADO_SUB_CANCELADA = "cancelada"
ESTADOS_SUBSTITUICAO = (
    ESTADO_SUB_AGUARDANDO,
    ESTADO_SUB_CONVOCADO,
    ESTADO_SUB_ATENDIDA,
    ESTADO_SUB_CANCELADA,
)

TIPOS_AUSENCIA = ("ferias", "atestado", "folga")


# ---------------------------------------------------------------------------
# Tabela associativa
# ---------------------------------------------------------------------------

profissional_especialidade = Table(
    "profissional_especialidade",
    Base.metadata,
    Column(
        "profissional_id",
        Integer,
        ForeignKey("profissionais.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "especialidade_id",
        Integer,
        ForeignKey("especialidades.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
)


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------


class Profissional(Base):
    """Membro da equipe que pode ser alocado em plantoes."""

    __tablename__ = "profissionais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    carga_semanal: Mapped[int] = mapped_column(Integer, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    horas_extras: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0"), server_default="0"
    )

    especialidades: Mapped[list["Especialidade"]] = relationship(
        secondary=profissional_especialidade,
        back_populates="profissionais",
        lazy="selectin",
    )
    plantoes: Mapped[list["Plantao"]] = relationship(
        back_populates="profissional", cascade="all, delete-orphan"
    )
    ausencias: Mapped[list["Ausencia"]] = relationship(
        back_populates="profissional", cascade="all, delete-orphan"
    )

    @property
    def especialidade_ids(self) -> set[int]:
        """Conjunto de identificadores das especialidades do profissional."""

        return {especialidade.id for especialidade in self.especialidades}


class Especialidade(Base):
    """Area de atuacao exigida por um turno."""

    __tablename__ = "especialidades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)

    profissionais: Mapped[list[Profissional]] = relationship(
        secondary=profissional_especialidade,
        back_populates="especialidades",
    )
    turnos: Mapped[list["Turno"]] = relationship(back_populates="especialidade")


class Turno(Base):
    """Janela de tempo que precisa de cobertura por uma especialidade."""

    __tablename__ = "turnos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    data_fim: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    especialidade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("especialidades.id"), nullable=False, index=True
    )
    cobertura_minima: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    especialidade: Mapped[Especialidade] = relationship(back_populates="turnos")
    plantoes: Mapped[list["Plantao"]] = relationship(
        back_populates="turno", cascade="all, delete-orphan", order_by="Plantao.id"
    )
    substituicoes: Mapped[list["Substituicao"]] = relationship(
        back_populates="turno", cascade="all, delete-orphan", order_by="Substituicao.posicao"
    )

    @property
    def intervalo(self) -> tuple[datetime, datetime]:
        """Intervalo semiaberto ``[data_inicio, data_fim)`` do turno."""

        return (self.data_inicio, self.data_fim)


class Plantao(Base):
    """Alocacao de um profissional em um turno."""

    __tablename__ = "plantoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turno_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("turnos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profissional_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profissionais.id", ondelete="CASCADE"), nullable=False, index=True
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ESTADO_PLANTAO_CONFIRMADO, index=True
    )

    turno: Mapped[Turno] = relationship(back_populates="plantoes")
    profissional: Mapped[Profissional] = relationship(back_populates="plantoes")

    @property
    def confirmado(self) -> bool:
        """Indica se o plantao esta em estado ``confirmado``."""

        return self.estado == ESTADO_PLANTAO_CONFIRMADO


class Troca(Base):
    """Solicitacao de permuta entre dois plantoes confirmados."""

    __tablename__ = "trocas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plantao_origem_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plantoes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plantao_destino_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plantoes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ESTADO_TROCA_SOLICITADA, index=True
    )
    data_solicitacao: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    data_decisao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    plantao_origem: Mapped[Plantao] = relationship(foreign_keys=[plantao_origem_id])
    plantao_destino: Mapped[Plantao] = relationship(foreign_keys=[plantao_destino_id])

    @property
    def pendente(self) -> bool:
        """Indica se a troca ainda aguarda decisao."""

        return self.estado == ESTADO_TROCA_SOLICITADA


class Substituicao(Base):
    """Posicao de um profissional na fila de substituicao de um turno."""

    __tablename__ = "substituicoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turno_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("turnos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profissional_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profissionais.id", ondelete="CASCADE"), nullable=False, index=True
    )
    posicao: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ESTADO_SUB_AGUARDANDO, index=True
    )

    turno: Mapped[Turno] = relationship(back_populates="substituicoes")
    profissional: Mapped[Profissional] = relationship()


class Ausencia(Base):
    """Periodo em que o profissional nao pode ser escalado."""

    __tablename__ = "ausencias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profissional_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profissionais.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    data_fim: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)

    profissional: Mapped[Profissional] = relationship(back_populates="ausencias")

    @property
    def intervalo(self) -> tuple[datetime, datetime]:
        """Intervalo semiaberto ``[data_inicio, data_fim)`` da ausencia."""

        return (self.data_inicio, self.data_fim)
