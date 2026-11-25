"""Constantes de dominio: estados, tipos e limites numericos.

Centralizar esses valores evita divergencia entre o esquema do banco, os
esquemas Pydantic e as regras de negocio.
"""

from __future__ import annotations

from typing import Final

# --- Estados --------------------------------------------------------------
PLANTAO_CONFIRMADO: Final = "confirmado"
PLANTAO_CANCELADO: Final = "cancelado"
ESTADOS_PLANTAO: Final = (PLANTAO_CONFIRMADO, PLANTAO_CANCELADO)

TROCA_SOLICITADA: Final = "solicitada"
TROCA_APROVADA: Final = "aprovada"
TROCA_REJEITADA: Final = "rejeitada"
ESTADOS_TROCA: Final = (TROCA_SOLICITADA, TROCA_APROVADA, TROCA_REJEITADA)

SUB_AGUARDANDO: Final = "aguardando"
SUB_CONVOCADO: Final = "convocado"
SUB_ATENDIDA: Final = "atendida"
SUB_CANCELADA: Final = "cancelada"
ESTADOS_SUBSTITUICAO: Final = (
    SUB_AGUARDANDO,
    SUB_CONVOCADO,
    SUB_ATENDIDA,
    SUB_CANCELADA,
)

AUSENCIA_FERIAS: Final = "ferias"
AUSENCIA_ATESTADO: Final = "atestado"
AUSENCIA_FOLGA: Final = "folga"
TIPOS_AUSENCIA: Final = (AUSENCIA_FERIAS, AUSENCIA_ATESTADO, AUSENCIA_FOLGA)

# --- Limites de dominio (secao 3) -----------------------------------------
NOME_MIN: Final = 1
NOME_MAX: Final = 120
EMAIL_MIN: Final = 13
EMAIL_MAX: Final = 120
ESPECIALIDADE_NOME_MIN: Final = 1
ESPECIALIDADE_NOME_MAX: Final = 60
CARGA_SEMANAL_MIN: Final = 20
CARGA_SEMANAL_MAX: Final = 44
TURNO_DURACAO_MIN_HORAS: Final = 4.0
TURNO_DURACAO_MAX_HORAS: Final = 12.0
#: Fator aplicado as horas de turnos noturnos em ``horas_periodo`` (RF23).
#: Nao afeta ``horas_extras`` nem o limite semanal de INV3.
ADICIONAL_NOTURNO: Final = 1.20

# --- Limites das invariantes ----------------------------------------------
#: INV2 - descanso minimo entre plantoes confirmados (11h e valido).
DESCANSO_MINIMO_HORAS: Final = 11.0
#: INV3 - teto absoluto de horas confirmadas por semana.
LIMITE_SEMANAL_HORAS: Final = 44.0
#: INV7 - numero maximo de dias civis consecutivos trabalhados.
MAX_DIAS_CONSECUTIVOS: Final = 6
#: Tolerancia das comparacoes de horas (ponto flutuante).
EPSILON_HORAS: Final = 1e-9

# --- Paginacao ------------------------------------------------------------
LIMITE_PADRAO: Final = 20
LIMITE_MAXIMO: Final = 100
DESLOCAMENTO_PADRAO: Final = 0
