"""Esquemas Pydantic v2 (entrada e saida da API).

As validacoes sintaticas da secao 3 da especificacao ficam aqui: violacoes
resultam em ``422`` (RF02, RF09). As regras que dependem do estado do banco
ficam em :mod:`app.regras`.

Todos os campos de data e hora sao normalizados para UTC *aware*, de modo
que a serializacao JSON produz ISO 8601 com sufixo ``Z``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from . import constantes as C
from .tempo import duracao_horas, para_utc

T = TypeVar("T")


def _normalizar(valor: datetime) -> datetime:
    """Garante UTC *aware* tanto na entrada quanto na saida."""

    return para_utc(valor)


def _nome_limpo(valor: str) -> str:
    """Remove espacos das bordas e recusa nomes em branco (RF02)."""

    limpo = valor.strip()
    if not limpo:
        raise ValueError("nome nao pode ser vazio")
    return limpo


def _email_limpo(valor: str) -> str:
    """Valida o e-mail apos a remocao dos espacos das bordas (RF02)."""

    limpo = valor.strip()
    if "@" not in limpo:
        raise ValueError("email deve conter '@'")
    if not C.EMAIL_MIN <= len(limpo) <= C.EMAIL_MAX:
        raise ValueError(
            f"email deve ter entre {C.EMAIL_MIN} e {C.EMAIL_MAX} caracteres"
        )
    return limpo


_NOME = AfterValidator(_nome_limpo)
_EMAIL = AfterValidator(_email_limpo)
_ESP_MIN, _ESP_MAX = C.ESPECIALIDADE_NOME_MIN, C.ESPECIALIDADE_NOME_MAX

#: ``datetime`` sempre interpretado e apresentado em UTC.
DataHora = Annotated[datetime, AfterValidator(_normalizar)]
#: Identificador de uma entidade referenciada.
Id = Annotated[int, Field(ge=1)]
Nome = Annotated[str, Field(min_length=C.NOME_MIN, max_length=C.NOME_MAX), _NOME]
NomeEspecialidade = Annotated[str, Field(min_length=_ESP_MIN, max_length=_ESP_MAX), _NOME]
Email = Annotated[str, Field(min_length=C.EMAIL_MIN, max_length=C.EMAIL_MAX), _EMAIL]
CargaSemanal = Annotated[int, Field(ge=C.CARGA_SEMANAL_MIN, le=C.CARGA_SEMANAL_MAX)]

EstadoPlantao = Literal["confirmado", "cancelado"]
EstadoTroca = Literal["solicitada", "aprovada", "rejeitada"]
EstadoSubstituicao = Literal["aguardando", "convocado", "atendida", "cancelada"]
TipoAusencia = Literal["ferias", "atestado", "folga"]


class Base(BaseModel):
    """Base dos esquemas, habilitando leitura a partir de objetos ORM."""

    model_config = ConfigDict(from_attributes=True)


class Pagina(Base, Generic[T]):
    """Envelope padrao de listagem, no formato ``{itens, total}``."""

    itens: list[T]
    total: int


# --- Especialidade --------------------------------------------------------
class EspecialidadeCriar(Base):
    """Dados de entrada de ``POST /especialidades`` (RF08)."""

    nome: NomeEspecialidade


class EspecialidadeResposta(Base):
    """Especialidade devolvida pela API."""

    id: int
    nome: str


# --- Profissional ---------------------------------------------------------
class ProfissionalCriar(Base):
    """Dados de entrada de ``POST /profissionais`` (RF01 e RF02)."""

    nome: Nome
    email: Email
    carga_semanal: CargaSemanal
    ativo: bool = True


class ProfissionalResposta(Base):
    """Profissional devolvido pela API, com suas especialidades."""

    id: int
    nome: str
    email: str
    carga_semanal: int
    ativo: bool
    horas_extras: float
    especialidades: list[EspecialidadeResposta] = Field(default_factory=list)


class VinculoEspecialidade(Base):
    """Corpo do vinculo de especialidade a um profissional (RF06)."""

    especialidade_id: Id


# --- Turno ----------------------------------------------------------------
class TurnoCriar(Base):
    """Dados de entrada de ``POST /turnos`` (RF09)."""

    data_inicio: DataHora
    data_fim: DataHora
    especialidade_id: Id
    cobertura_minima: int = Field(default=1, ge=1)
    noturno: bool = False

    @model_validator(mode="after")
    def _validar_duracao(self) -> "TurnoCriar":
        if self.data_fim <= self.data_inicio:
            raise ValueError("data_fim deve ser posterior a data_inicio")
        total = duracao_horas(self.data_inicio, self.data_fim)
        if total < C.TURNO_DURACAO_MIN_HORAS - C.EPSILON_HORAS:
            raise ValueError(
                f"duracao do turno deve ser de no minimo "
                f"{C.TURNO_DURACAO_MIN_HORAS:g} horas"
            )
        if total > C.TURNO_DURACAO_MAX_HORAS + C.EPSILON_HORAS:
            raise ValueError(
                f"duracao do turno deve ser de no maximo "
                f"{C.TURNO_DURACAO_MAX_HORAS:g} horas"
            )
        return self


class TurnoResposta(Base):
    """Turno devolvido pela API."""

    id: int
    data_inicio: DataHora
    data_fim: DataHora
    especialidade_id: int
    cobertura_minima: int
    noturno: bool = False


# --- Plantao e escala -----------------------------------------------------
class PlantaoCriar(Base):
    """Dados de entrada de ``POST /plantoes`` (RF13)."""

    turno_id: Id
    profissional_id: Id


class PlantaoResposta(Base):
    """Plantao devolvido pela API."""

    id: int
    turno_id: int
    profissional_id: int
    estado: EstadoPlantao


class TurnoDetalhe(TurnoResposta):
    """Turno com sua lista de plantoes (RF11)."""

    plantoes: list[PlantaoResposta] = Field(default_factory=list)


class ItemEscala(Base):
    """Plantao da escala de um profissional, com os dados do turno (RF23)."""

    id: int
    turno_id: int
    profissional_id: int
    estado: EstadoPlantao
    data_inicio: DataHora
    data_fim: DataHora
    especialidade_id: int
    horas: float


class EscalaResposta(Base):
    """Envelope da escala, no formato ``{itens, total, horas_periodo}``."""

    itens: list[ItemEscala]
    total: int
    horas_periodo: float


# --- Troca ----------------------------------------------------------------
class TrocaCriar(Base):
    """Dados de entrada de ``POST /trocas`` (RF24)."""

    plantao_origem_id: Id
    plantao_destino_id: Id


class TrocaResposta(Base):
    """Troca devolvida pela API."""

    id: int
    plantao_origem_id: int
    plantao_destino_id: int
    estado: EstadoTroca
    data_solicitacao: DataHora
    data_decisao: DataHora | None = None


# --- Substituicao e ausencia ----------------------------------------------
class SubstituicaoCriar(Base):
    """Dados de entrada de ``POST /substituicoes`` (RF30)."""

    turno_id: Id
    profissional_id: Id


class SubstituicaoResposta(Base):
    """Substituicao devolvida pela API."""

    id: int
    turno_id: int
    profissional_id: int
    posicao: int
    estado: EstadoSubstituicao


class AusenciaCriar(Base):
    """Dados de entrada de ``POST /ausencias`` (RF35)."""

    profissional_id: Id
    data_inicio: DataHora
    data_fim: DataHora
    tipo: TipoAusencia

    @model_validator(mode="after")
    def _validar_periodo(self) -> "AusenciaCriar":
        if self.data_fim <= self.data_inicio:
            raise ValueError("data_fim deve ser posterior a data_inicio")
        return self


class AusenciaResposta(Base):
    """Ausencia devolvida pela API."""

    id: int
    profissional_id: int
    data_inicio: DataHora
    data_fim: DataHora
    tipo: TipoAusencia


# --- Auditoria ------------------------------------------------------------
class AuditoriaResposta(Base):
    """Registro de auditoria devolvido por ``GET /auditoria``."""

    id: int
    metodo: str
    caminho: str
    perfil: str
    codigo_resposta: int
    instante: DataHora
