"""Vocabulario de estados e tipos usados no dominio (secao 3)."""

from __future__ import annotations

from typing import Final, Literal

# --- Plantao --------------------------------------------------------------

PLANTAO_CONFIRMADO: Final = "confirmado"
PLANTAO_CANCELADO: Final = "cancelado"
ESTADOS_PLANTAO: Final = (PLANTAO_CONFIRMADO, PLANTAO_CANCELADO)

EstadoPlantao = Literal["confirmado", "cancelado"]

# --- Troca ----------------------------------------------------------------

TROCA_SOLICITADA: Final = "solicitada"
TROCA_APROVADA: Final = "aprovada"
TROCA_REJEITADA: Final = "rejeitada"
ESTADOS_TROCA: Final = (TROCA_SOLICITADA, TROCA_APROVADA, TROCA_REJEITADA)

EstadoTroca = Literal["solicitada", "aprovada", "rejeitada"]

# --- Substituicao ---------------------------------------------------------

SUBSTITUICAO_AGUARDANDO: Final = "aguardando"
SUBSTITUICAO_CONVOCADO: Final = "convocado"
SUBSTITUICAO_ATENDIDA: Final = "atendida"
SUBSTITUICAO_CANCELADA: Final = "cancelada"
ESTADOS_SUBSTITUICAO: Final = (
    SUBSTITUICAO_AGUARDANDO,
    SUBSTITUICAO_CONVOCADO,
    SUBSTITUICAO_ATENDIDA,
    SUBSTITUICAO_CANCELADA,
)

EstadoSubstituicao = Literal["aguardando", "convocado", "atendida", "cancelada"]

# --- Ausencia -------------------------------------------------------------

AUSENCIA_FERIAS: Final = "ferias"
AUSENCIA_ATESTADO: Final = "atestado"
AUSENCIA_FOLGA: Final = "folga"
TIPOS_AUSENCIA: Final = (AUSENCIA_FERIAS, AUSENCIA_ATESTADO, AUSENCIA_FOLGA)

TipoAusencia = Literal["ferias", "atestado", "folga"]
