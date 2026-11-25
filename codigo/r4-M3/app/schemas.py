"""Schemas Pydantic v2 (entrada e saida da API).

Todas as datas sao normalizadas para UTC. Valores sem fuso sao interpretados
como ja expressos em UTC, conforme a secao 2 da especificacao.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.tempo import DURACAO_MAXIMA_SEGUNDOS, DURACAO_MINIMA_SEGUNDOS, duracao_segundos


def _para_utc(valor: datetime) -> datetime:
    """Garante que o ``datetime`` carregue o fuso UTC."""

    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


#: ``datetime`` sempre apresentado/aceito em UTC.
DataHora = Annotated[datetime, AfterValidator(_para_utc)]

EstadoPlantao = Literal["confirmado", "cancelado"]
EstadoTroca = Literal["solicitada", "aprovada", "rejeitada"]
EstadoSubstituicao = Literal["aguardando", "convocado", "atendida", "cancelada"]
TipoAusencia = Literal["ferias", "atestado", "folga"]


class Base(BaseModel):
    """Base comum: leitura a partir de objetos ORM."""

    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Pagina(Base, Generic[T]):
    """Envelope padrao de listagem."""

    itens: list[T]
    total: int


# ---------------------------------------------------------------------------
# Profissional
# ---------------------------------------------------------------------------


class ProfissionalCriar(Base):
    """Dados aceitos no cadastro de um profissional (RF01/RF02)."""

    nome: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=13, max_length=120)
    carga_semanal: int = Field(ge=20, le=44)
    ativo: bool = True

    @field_validator("email")
    @classmethod
    def _validar_email(cls, valor: str) -> str:
        if "@" not in valor:
            raise ValueError("email deve conter '@'")
        return valor

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("nome nao pode ser vazio")
        return valor


class ProfissionalSaida(Base):
    """Representacao de um profissional nas respostas da API."""

    id: int
    nome: str
    email: str
    carga_semanal: int
    ativo: bool
    horas_extras: float
    especialidades: list[int] = Field(default_factory=list)

    @field_validator("horas_extras", mode="before")
    @classmethod
    def _converter_decimal(cls, valor: Decimal | float | None) -> float:
        if valor is None:
            return 0.0
        return round(float(valor), 2)

    @field_validator("especialidades", mode="before")
    @classmethod
    def _ids_especialidades(cls, valor: object) -> list[int]:
        if valor is None:
            return []
        ids: list[int] = []
        for item in valor:  # type: ignore[union-attr]
            ids.append(item if isinstance(item, int) else item.id)
        return sorted(ids)


# ---------------------------------------------------------------------------
# Especialidade
# ---------------------------------------------------------------------------


class EspecialidadeCriar(Base):
    """Dados aceitos no cadastro de uma especialidade (RF08)."""

    nome: str = Field(min_length=1, max_length=60)

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("nome nao pode ser vazio")
        return valor


class EspecialidadeSaida(Base):
    """Representacao de uma especialidade nas respostas da API."""

    id: int
    nome: str


class VinculoEspecialidade(Base):
    """Corpo do vinculo entre profissional e especialidade (RF06)."""

    especialidade_id: int = Field(ge=1)


class VinculoSaida(Base):
    """Vinculo criado entre profissional e especialidade."""

    profissional_id: int
    especialidade_id: int


# ---------------------------------------------------------------------------
# Turno
# ---------------------------------------------------------------------------


class TurnoCriar(Base):
    """Dados aceitos no cadastro de um turno (RF09)."""

    data_inicio: DataHora
    data_fim: DataHora
    especialidade_id: int = Field(ge=1)
    cobertura_minima: int = Field(ge=1)

    @model_validator(mode="after")
    def _validar_duracao(self) -> "TurnoCriar":
        if self.data_fim <= self.data_inicio:
            raise ValueError("data_fim deve ser posterior a data_inicio")
        segundos = duracao_segundos(self.data_inicio, self.data_fim)
        if segundos < DURACAO_MINIMA_SEGUNDOS or segundos > DURACAO_MAXIMA_SEGUNDOS:
            raise ValueError("duracao do turno deve estar entre 4 e 12 horas")
        return self


class TurnoSaida(Base):
    """Representacao de um turno nas respostas da API."""

    id: int
    data_inicio: DataHora
    data_fim: DataHora
    especialidade_id: int
    cobertura_minima: int


class PlantaoSaida(Base):
    """Representacao de um plantao nas respostas da API."""

    id: int
    turno_id: int
    profissional_id: int
    estado: EstadoPlantao


class TurnoDetalhe(TurnoSaida):
    """Turno acompanhado da sua lista de plantoes (RF11)."""

    plantoes: list[PlantaoSaida] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Plantao e escala
# ---------------------------------------------------------------------------


class PlantaoCriar(Base):
    """Dados aceitos na alocacao de um profissional em um turno (RF13)."""

    turno_id: int = Field(ge=1)
    profissional_id: int = Field(ge=1)


class ItemEscalaSaida(Base):
    """Plantao da escala, enriquecido com os dados do turno (RF23)."""

    id: int
    turno_id: int
    profissional_id: int
    estado: EstadoPlantao
    data_inicio: DataHora
    data_fim: DataHora
    especialidade_id: int
    horas: float


class EscalaSaida(Base):
    """Envelope da escala de um profissional no periodo consultado."""

    itens: list[ItemEscalaSaida]
    total: int
    horas_periodo: float


# ---------------------------------------------------------------------------
# Troca
# ---------------------------------------------------------------------------


class TrocaCriar(Base):
    """Dados aceitos na solicitacao de troca entre plantoes (RF24)."""

    plantao_origem_id: int = Field(ge=1)
    plantao_destino_id: int = Field(ge=1)


class TrocaSaida(Base):
    """Representacao de uma troca nas respostas da API."""

    id: int
    plantao_origem_id: int
    plantao_destino_id: int
    estado: EstadoTroca
    data_solicitacao: DataHora
    data_decisao: DataHora | None = None


# ---------------------------------------------------------------------------
# Substituicao
# ---------------------------------------------------------------------------


class SubstituicaoCriar(Base):
    """Dados aceitos na entrada da fila de substituicao (RF30)."""

    turno_id: int = Field(ge=1)
    profissional_id: int = Field(ge=1)


class SubstituicaoSaida(Base):
    """Representacao de uma substituicao nas respostas da API."""

    id: int
    turno_id: int
    profissional_id: int
    posicao: int
    estado: EstadoSubstituicao


# ---------------------------------------------------------------------------
# Ausencia
# ---------------------------------------------------------------------------


class AusenciaCriar(Base):
    """Dados aceitos no registro de uma ausencia (RF35)."""

    profissional_id: int = Field(ge=1)
    data_inicio: DataHora
    data_fim: DataHora
    tipo: TipoAusencia

    @model_validator(mode="after")
    def _validar_periodo(self) -> "AusenciaCriar":
        if self.data_fim <= self.data_inicio:
            raise ValueError("data_fim deve ser posterior a data_inicio")
        return self


class AusenciaSaida(Base):
    """Representacao de uma ausencia nas respostas da API."""

    id: int
    profissional_id: int
    data_inicio: DataHora
    data_fim: DataHora
    tipo: TipoAusencia
