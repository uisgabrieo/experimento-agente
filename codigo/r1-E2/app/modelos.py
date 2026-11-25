"""Modelos SQLAlchemy.

Os nomes de tabelas e colunas listados na secao 2.1 da especificacao fazem
parte do contrato da aplicacao e sao mantidos exatamente como definidos.
Colunas auxiliares (``criado_em``) sao permitidas pela mesma secao.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import constantes as C
from .banco import Base, engine
from .tempo import agora

#: Vinculo N:N entre profissionais e especialidades.
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


class Profissional(Base):  # pylint: disable=too-few-public-methods
    """Membro da equipe que pode receber plantoes."""

    __tablename__ = "profissionais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(C.NOME_MAX), nullable=False)
    email: Mapped[str] = mapped_column(
        String(C.EMAIL_MAX), nullable=False, unique=True, index=True
    )
    carga_semanal: Mapped[int] = mapped_column(Integer, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    horas_extras: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0")
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora)

    especialidades: Mapped[list["Especialidade"]] = relationship(
        "Especialidade",
        secondary=profissional_especialidade,
        back_populates="profissionais",
        lazy="selectin",
    )
    plantoes: Mapped[list["Plantao"]] = relationship(
        "Plantao", back_populates="profissional", lazy="select"
    )
    ausencias: Mapped[list["Ausencia"]] = relationship(
        "Ausencia", back_populates="profissional", lazy="select"
    )

    def tem_especialidade(self, especialidade_id: int) -> bool:
        """Indica se o profissional possui a especialidade informada (INV4)."""
        return any(e.id == especialidade_id for e in self.especialidades)


class Especialidade(Base):  # pylint: disable=too-few-public-methods
    """Especialidade medica exigida por um turno."""

    __tablename__ = "especialidades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(
        String(C.ESPECIALIDADE_NOME_MAX), nullable=False, unique=True, index=True
    )

    profissionais: Mapped[list[Profissional]] = relationship(
        "Profissional",
        secondary=profissional_especialidade,
        back_populates="especialidades",
        lazy="select",
    )
    turnos: Mapped[list["Turno"]] = relationship(
        "Turno", back_populates="especialidade", lazy="select"
    )


class Turno(Base):  # pylint: disable=too-few-public-methods
    """Janela de tempo que precisa de cobertura por uma especialidade."""

    __tablename__ = "turnos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    data_fim: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    especialidade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("especialidades.id"), nullable=False, index=True
    )
    cobertura_minima: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Turno noturno: suas horas recebem adicional em ``horas_periodo`` (RF23).
    noturno: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    especialidade: Mapped[Especialidade] = relationship(
        "Especialidade", back_populates="turnos", lazy="joined"
    )
    plantoes: Mapped[list["Plantao"]] = relationship(
        "Plantao", back_populates="turno", lazy="select"
    )
    substituicoes: Mapped[list["Substituicao"]] = relationship(
        "Substituicao", back_populates="turno", lazy="select"
    )


class Plantao(Base):  # pylint: disable=too-few-public-methods
    """Alocacao de um profissional em um turno."""

    __tablename__ = "plantoes"
    __table_args__ = (
        Index("ix_plantoes_profissional_estado", "profissional_id", "estado"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turno_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("turnos.id"), nullable=False, index=True
    )
    profissional_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profissionais.id"), nullable=False, index=True
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default=C.PLANTAO_CONFIRMADO
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora)

    turno: Mapped[Turno] = relationship(
        "Turno", back_populates="plantoes", lazy="joined"
    )
    profissional: Mapped[Profissional] = relationship(
        "Profissional", back_populates="plantoes", lazy="select"
    )


class Troca(Base):  # pylint: disable=too-few-public-methods
    """Solicitacao de permuta entre dois plantoes confirmados."""

    __tablename__ = "trocas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plantao_origem_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plantoes.id"), nullable=False, index=True
    )
    plantao_destino_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plantoes.id"), nullable=False, index=True
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default=C.TROCA_SOLICITADA, index=True
    )
    data_solicitacao: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=agora
    )
    data_decisao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    plantao_origem: Mapped[Plantao] = relationship(
        "Plantao", foreign_keys=[plantao_origem_id], lazy="select"
    )
    plantao_destino: Mapped[Plantao] = relationship(
        "Plantao", foreign_keys=[plantao_destino_id], lazy="select"
    )


class Substituicao(Base):  # pylint: disable=too-few-public-methods
    """Posicao de um profissional na fila de substituicao de um turno."""

    __tablename__ = "substituicoes"
    __table_args__ = (
        Index("ix_substituicoes_turno_estado", "turno_id", "estado", "posicao"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turno_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("turnos.id"), nullable=False, index=True
    )
    profissional_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profissionais.id"), nullable=False, index=True
    )
    posicao: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default=C.SUB_AGUARDANDO
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora)

    turno: Mapped[Turno] = relationship(
        "Turno", back_populates="substituicoes", lazy="select"
    )
    profissional: Mapped[Profissional] = relationship("Profissional", lazy="select")


class Ausencia(Base):  # pylint: disable=too-few-public-methods
    """Periodo em que um profissional nao pode ser alocado."""

    __tablename__ = "ausencias"
    __table_args__ = (
        Index("ix_ausencias_profissional_periodo", "profissional_id", "data_inicio"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profissional_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profissionais.id"), nullable=False, index=True
    )
    data_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    data_fim: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)

    profissional: Mapped[Profissional] = relationship(
        "Profissional", back_populates="ausencias", lazy="select"
    )


class Auditoria(Base):  # pylint: disable=too-few-public-methods
    """Registro de uma requisicao a operacao de escrita."""

    __tablename__ = "auditoria"
    __table_args__ = (Index("ix_auditoria_instante", "instante"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metodo: Mapped[str] = mapped_column(String(10), nullable=False)
    caminho: Mapped[str] = mapped_column(String(255), nullable=False)
    perfil: Mapped[str] = mapped_column(String(20), nullable=False)
    codigo_resposta: Mapped[int] = mapped_column(Integer, nullable=False)
    instante: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora)


def _acrescentar_colunas_ausentes() -> None:
    """Acrescenta colunas novas a bancos criados por versoes anteriores.

    ``create_all`` nao altera tabelas existentes; sem isso, um ``escala.db``
    antigo ficaria sem a coluna ``turnos.noturno``.
    """

    inspetor = inspect(engine)
    if "turnos" not in inspetor.get_table_names():
        return
    colunas = {coluna["name"] for coluna in inspetor.get_columns("turnos")}
    if "noturno" in colunas:
        return
    with engine.begin() as conexao:
        conexao.execute(
            text("ALTER TABLE turnos ADD COLUMN noturno BOOLEAN NOT NULL DEFAULT 0")
        )


def criar_tabelas() -> None:
    """Cria o esquema do banco, caso ainda nao exista."""

    Base.metadata.create_all(bind=engine)
    _acrescentar_colunas_ausentes()
