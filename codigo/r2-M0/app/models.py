"""Modelos ORM.

Os nomes de tabelas e colunas obrigatorios da secao 2.1 da especificacao
sao contrato e estao reproduzidos literalmente aqui. Colunas adicionais
(``criado_em``, por exemplo) sao permitidas pela propria secao.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .estados import (
    ESTADOS_PLANTAO,
    ESTADOS_SUBSTITUICAO,
    ESTADOS_TROCA,
    PLANTAO_CONFIRMADO,
    SUBSTITUICAO_AGUARDANDO,
    TIPOS_AUSENCIA,
    TROCA_SOLICITADA,
)
from .tempo import agora_utc


def _em(coluna: str, valores: tuple[str, ...]) -> str:
    """Monta a expressao SQL ``coluna IN (...)`` para um CheckConstraint."""

    lista = ", ".join(f"'{valor}'" for valor in valores)
    return f"{coluna} IN ({lista})"


# --- Tabela de associacao -------------------------------------------------

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


# --- Entidades ------------------------------------------------------------


class Profissional(Base):
    __tablename__ = "profissionais"
    __table_args__ = (
        CheckConstraint("carga_semanal BETWEEN 20 AND 44", name="ck_prof_carga"),
        CheckConstraint("length(nome) BETWEEN 1 AND 120", name="ck_prof_nome"),
        CheckConstraint("horas_extras >= 0", name="ck_prof_horas_extras"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    carga_semanal: Mapped[int] = mapped_column(Integer, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    horas_extras: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False), nullable=False, default=0
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=agora_utc
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

    def tem_especialidade(self, especialidade_id: int) -> bool:
        return any(esp.id == especialidade_id for esp in self.especialidades)

    @property
    def especialidade_ids(self) -> list[int]:
        return sorted(esp.id for esp in self.especialidades)


class Especialidade(Base):
    __tablename__ = "especialidades"
    __table_args__ = (
        CheckConstraint("length(nome) BETWEEN 1 AND 60", name="ck_esp_nome"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)

    profissionais: Mapped[list[Profissional]] = relationship(
        secondary=profissional_especialidade,
        back_populates="especialidades",
    )
    turnos: Mapped[list["Turno"]] = relationship(back_populates="especialidade")


class Turno(Base):
    __tablename__ = "turnos"
    __table_args__ = (
        CheckConstraint("data_fim > data_inicio", name="ck_turno_ordem"),
        CheckConstraint("cobertura_minima >= 1", name="ck_turno_cobertura"),
        Index("ix_turnos_periodo", "data_inicio", "data_fim"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    data_fim: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    especialidade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("especialidades.id"), nullable=False, index=True
    )
    cobertura_minima: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    especialidade: Mapped[Especialidade] = relationship(back_populates="turnos")
    plantoes: Mapped[list["Plantao"]] = relationship(
        back_populates="turno", cascade="all, delete-orphan", lazy="selectin"
    )
    substituicoes: Mapped[list["Substituicao"]] = relationship(
        back_populates="turno", cascade="all, delete-orphan", lazy="selectin"
    )


class Plantao(Base):
    __tablename__ = "plantoes"
    __table_args__ = (
        CheckConstraint(_em("estado", ESTADOS_PLANTAO), name="ck_plantao_estado"),
        Index("ix_plantoes_prof_estado", "profissional_id", "estado"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turno_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("turnos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profissional_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profissionais.id"), nullable=False, index=True
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PLANTAO_CONFIRMADO
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=agora_utc
    )

    turno: Mapped[Turno] = relationship(back_populates="plantoes")
    profissional: Mapped[Profissional] = relationship(back_populates="plantoes")


class Troca(Base):
    __tablename__ = "trocas"
    __table_args__ = (
        CheckConstraint(_em("estado", ESTADOS_TROCA), name="ck_troca_estado"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plantao_origem_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plantoes.id"), nullable=False, index=True
    )
    plantao_destino_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plantoes.id"), nullable=False, index=True
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TROCA_SOLICITADA
    )
    data_solicitacao: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=agora_utc
    )
    data_decisao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    plantao_origem: Mapped[Plantao] = relationship(foreign_keys=[plantao_origem_id])
    plantao_destino: Mapped[Plantao] = relationship(foreign_keys=[plantao_destino_id])


class Substituicao(Base):
    __tablename__ = "substituicoes"
    __table_args__ = (
        CheckConstraint(
            _em("estado", ESTADOS_SUBSTITUICAO), name="ck_substituicao_estado"
        ),
        CheckConstraint("posicao >= 1", name="ck_substituicao_posicao"),
        Index("ix_substituicoes_turno_estado", "turno_id", "estado", "posicao"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turno_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("turnos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profissional_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profissionais.id"), nullable=False, index=True
    )
    posicao: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SUBSTITUICAO_AGUARDANDO
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=agora_utc
    )

    turno: Mapped[Turno] = relationship(back_populates="substituicoes")
    profissional: Mapped[Profissional] = relationship()


class Ausencia(Base):
    __tablename__ = "ausencias"
    __table_args__ = (
        CheckConstraint(_em("tipo", TIPOS_AUSENCIA), name="ck_ausencia_tipo"),
        CheckConstraint("data_fim > data_inicio", name="ck_ausencia_ordem"),
        UniqueConstraint(
            "profissional_id",
            "data_inicio",
            "data_fim",
            "tipo",
            name="uq_ausencia_periodo",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profissional_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profissionais.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    data_fim: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)

    profissional: Mapped[Profissional] = relationship(back_populates="ausencias")
