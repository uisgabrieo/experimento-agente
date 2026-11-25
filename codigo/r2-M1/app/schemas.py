"""Esquemas Pydantic v2 de entrada e saida (secoes 3 e 5)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, Optional, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    field_validator,
    model_validator,
)

from .estados import EstadoPlantao, EstadoSubstituicao, EstadoTroca, TipoAusencia
from .tempo import (
    DURACAO_MAXIMA_TURNO_HORAS,
    DURACAO_MINIMA_TURNO_HORAS,
    duracao_horas,
    para_utc_aware,
    para_utc_naive,
)

# --- Tipos auxiliares -----------------------------------------------------


def _normalizar_entrada(valor: datetime) -> datetime:
    """Datas de entrada sao convertidas para UTC *naive*."""

    return para_utc_naive(valor)


def _serializar(valor: datetime) -> str:
    return para_utc_aware(valor).isoformat()


def _serializar_opcional(valor: datetime | None) -> str | None:
    return None if valor is None else _serializar(valor)


DataHoraEntrada = Annotated[datetime, AfterValidator(_normalizar_entrada)]
DataHoraSaida = Annotated[
    datetime, PlainSerializer(_serializar, return_type=str, when_used="json")
]
DataHoraSaidaOpcional = Annotated[
    Optional[datetime],
    PlainSerializer(_serializar_opcional, return_type=Optional[str], when_used="json"),
]

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
NomeEspecialidade = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)
]
Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=13, max_length=120)]
CargaSemanal = Annotated[int, Field(ge=20, le=44)]
Cobertura = Annotated[int, Field(ge=1)]

T = TypeVar("T")


class Base(BaseModel):
    """Base comum: leitura a partir de objetos ORM."""

    model_config = ConfigDict(from_attributes=True)


class Pagina(Base, Generic[T]):
    """Envelope ``{itens, total}`` usado nas listagens."""

    itens: list[T]
    total: int


# --- Profissional ---------------------------------------------------------


class ProfissionalCriar(Base):
    """Corpo de ``POST /profissionais`` (RF01, RF02)."""

    nome: Nome
    email: Email
    carga_semanal: CargaSemanal
    ativo: bool = True

    @field_validator("email")
    @classmethod
    def _validar_email(cls, valor: str) -> str:
        if "@" not in valor:
            raise ValueError("email deve conter '@'")
        return valor


class EspecialidadeSaida(Base):
    """Especialidade como aparece nas respostas."""

    id: int
    nome: str


class ProfissionalSaida(Base):
    """Profissional retornado pelas rotas de consulta."""

    id: int
    nome: str
    email: str
    carga_semanal: int
    ativo: bool
    horas_extras: float
    especialidades: list[EspecialidadeSaida] = Field(default_factory=list)

    @field_validator("horas_extras", mode="before")
    @classmethod
    def _arredondar(cls, valor: float) -> float:
        return round(float(valor or 0.0), 2)


# --- Especialidade --------------------------------------------------------


class EspecialidadeCriar(Base):
    """Corpo de ``POST /especialidades`` (RF08)."""

    nome: NomeEspecialidade


class VinculoEspecialidade(Base):
    """Corpo do vinculo de especialidade ao profissional (RF06)."""

    especialidade_id: int = Field(ge=1)


# --- Turno ----------------------------------------------------------------


class TurnoCriar(Base):
    """Corpo de ``POST /turnos``, com validacao de duracao (RF09)."""

    data_inicio: DataHoraEntrada
    data_fim: DataHoraEntrada
    especialidade_id: int = Field(ge=1)
    cobertura_minima: Cobertura = 1

    @model_validator(mode="after")
    def _validar_duracao(self) -> "TurnoCriar":
        if self.data_fim <= self.data_inicio:
            raise ValueError("data_fim deve ser posterior a data_inicio")
        horas = duracao_horas(self.data_inicio, self.data_fim)
        if horas < DURACAO_MINIMA_TURNO_HORAS or horas > DURACAO_MAXIMA_TURNO_HORAS:
            raise ValueError(
                "duracao do turno deve estar entre "
                f"{DURACAO_MINIMA_TURNO_HORAS:.0f} e "
                f"{DURACAO_MAXIMA_TURNO_HORAS:.0f} horas (recebido {horas:.2f})"
            )
        return self


class PlantaoSaida(Base):
    """Plantao como aparece nas respostas."""

    id: int
    turno_id: int
    profissional_id: int
    estado: EstadoPlantao


class TurnoSaida(Base):
    """Turno como aparece nas listagens."""

    id: int
    data_inicio: DataHoraSaida
    data_fim: DataHoraSaida
    especialidade_id: int
    cobertura_minima: int


class TurnoDetalhe(TurnoSaida):
    """Turno com seus plantoes e a cobertura atual (RF11)."""

    plantoes: list[PlantaoSaida] = Field(default_factory=list)
    cobertura_atual: int = 0


# --- Plantao --------------------------------------------------------------


class PlantaoCriar(Base):
    """Corpo de ``POST /plantoes`` (RF13)."""

    turno_id: int = Field(ge=1)
    profissional_id: int = Field(ge=1)


# --- Troca ----------------------------------------------------------------


class TrocaCriar(Base):
    """Corpo de ``POST /trocas`` (RF24)."""

    plantao_origem_id: int = Field(ge=1)
    plantao_destino_id: int = Field(ge=1)


class TrocaSaida(Base):
    """Troca como aparece nas respostas."""

    id: int
    plantao_origem_id: int
    plantao_destino_id: int
    estado: EstadoTroca
    data_solicitacao: DataHoraSaida
    data_decisao: DataHoraSaidaOpcional = None


# --- Substituicao ---------------------------------------------------------


class SubstituicaoCriar(Base):
    """Corpo de ``POST /substituicoes`` (RF30)."""

    turno_id: int = Field(ge=1)
    profissional_id: int = Field(ge=1)


class SubstituicaoSaida(Base):
    """Substituicao como aparece nas respostas."""

    id: int
    turno_id: int
    profissional_id: int
    posicao: int
    estado: EstadoSubstituicao


class AceiteSaida(PlantaoSaida):
    """Resposta de ``POST /substituicoes/{id}/aceite`` (RF34).

    Representa o plantao criado; a substituicao atendida vem anexada por
    conveniencia.
    """

    substituicao: SubstituicaoSaida


# --- Ausencia -------------------------------------------------------------


class AusenciaCriar(Base):
    """Corpo de ``POST /ausencias`` (RF35)."""

    profissional_id: int = Field(ge=1)
    data_inicio: DataHoraEntrada
    data_fim: DataHoraEntrada
    tipo: TipoAusencia

    @model_validator(mode="after")
    def _validar_ordem(self) -> "AusenciaCriar":
        if self.data_fim <= self.data_inicio:
            raise ValueError("data_fim deve ser posterior a data_inicio")
        return self


class AusenciaSaida(Base):
    """Ausencia como aparece nas respostas."""

    id: int
    profissional_id: int
    data_inicio: DataHoraSaida
    data_fim: DataHoraSaida
    tipo: TipoAusencia


# --- Escala ---------------------------------------------------------------


class EscalaItem(Base):
    """Um plantao na escala do profissional, com suas horas."""

    plantao_id: int
    turno_id: int
    profissional_id: int
    estado: EstadoPlantao
    data_inicio: DataHoraSaida
    data_fim: DataHoraSaida
    especialidade_id: int
    horas: float


class EscalaSaida(Base):
    """Envelope ``{itens, total, horas_periodo}`` da escala (RF23)."""

    itens: list[EscalaItem]
    total: int
    horas_periodo: float
