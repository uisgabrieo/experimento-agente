"""Convencoes temporais (secao 4.1 da especificacao).

Intervalos sao semiabertos ``[inicio, fim)``; fim igual a inicio nao e
sobreposicao; a semana comeca na segunda-feira as 00:00 UTC; o dia civil
considerado e o dia UTC.

Internamente todos os ``datetime`` circulam como *naive* em UTC (a
representacao escolhida para o armazenamento em SQLite). As funcoes abaixo
aceitam valores com ou sem ``tzinfo`` e normalizam antes de calcular.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# --- Constantes de negocio ------------------------------------------------

HORAS_DESCANSO_MINIMO = 11
LIMITE_HORAS_SEMANAIS = 44.0
MAX_DIAS_CONSECUTIVOS = 6
DURACAO_MINIMA_TURNO_HORAS = 4.0
DURACAO_MAXIMA_TURNO_HORAS = 12.0

DESCANSO_MINIMO = timedelta(hours=HORAS_DESCANSO_MINIMO)
UMA_SEMANA = timedelta(days=7)
UM_DIA = timedelta(days=1)

# Tolerancia para comparacoes de ponto flutuante em horas (~0,036 s).
EPSILON_HORAS = 1e-5


# --- Normalizacao ---------------------------------------------------------


def agora_utc() -> datetime:
    """Instante atual em UTC, sem ``tzinfo`` (padrao de armazenamento)."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def para_utc_naive(valor: datetime) -> datetime:
    """Converte para UTC e remove o ``tzinfo``.

    Valores sem ``tzinfo`` sao interpretados como ja estando em UTC.
    """

    if valor.tzinfo is None:
        return valor
    return valor.astimezone(timezone.utc).replace(tzinfo=None)


def para_utc_aware(valor: datetime) -> datetime:
    """Converte para UTC mantendo o ``tzinfo`` explicito.

    Usado na serializacao das respostas, para que o ISO 8601 emitido deixe
    claro que o instante esta em UTC.
    """

    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


# --- Operacoes com intervalos --------------------------------------------


def duracao_horas(inicio: datetime, fim: datetime) -> float:
    """Duracao de ``[inicio, fim)`` em horas."""

    inicio = para_utc_naive(inicio)
    fim = para_utc_naive(fim)
    return (fim - inicio).total_seconds() / 3600.0


def intervalos_sobrepoem(
    inicio_a: datetime,
    fim_a: datetime,
    inicio_b: datetime,
    fim_b: datetime,
) -> bool:
    """Indica se ``[inicio_a, fim_a)`` e ``[inicio_b, fim_b)`` se sobrepoem."""

    inicio_a = para_utc_naive(inicio_a)
    fim_a = para_utc_naive(fim_a)
    inicio_b = para_utc_naive(inicio_b)
    fim_b = para_utc_naive(fim_b)
    return inicio_a < fim_b and inicio_b < fim_a


def intersecao(
    inicio_a: datetime,
    fim_a: datetime,
    inicio_b: datetime,
    fim_b: datetime,
) -> tuple[datetime, datetime] | None:
    """Intersecao semiaberta dos dois intervalos, ou ``None`` se vazia."""

    inicio_a = para_utc_naive(inicio_a)
    fim_a = para_utc_naive(fim_a)
    inicio_b = para_utc_naive(inicio_b)
    fim_b = para_utc_naive(fim_b)
    inicio = max(inicio_a, inicio_b)
    fim = min(fim_a, fim_b)
    if inicio >= fim:
        return None
    return inicio, fim


# --- Semanas --------------------------------------------------------------


def inicio_da_semana(valor: datetime) -> datetime:
    """Segunda-feira 00:00 UTC da semana que contem ``valor``."""

    valor = para_utc_naive(valor)
    dia = datetime(valor.year, valor.month, valor.day)
    return dia - timedelta(days=dia.weekday())


def semanas_do_intervalo(inicio: datetime, fim: datetime) -> list[datetime]:
    """Lista dos inicios de semana tocados por ``[inicio, fim)``."""

    inicio = para_utc_naive(inicio)
    fim = para_utc_naive(fim)
    if fim <= inicio:
        return []
    semanas: list[datetime] = []
    atual = inicio_da_semana(inicio)
    while atual < fim:
        semanas.append(atual)
        atual = atual + UMA_SEMANA
    return semanas


def horas_por_semana(
    intervalos: list[tuple[datetime, datetime]],
) -> dict[datetime, float]:
    """Distribui as horas dos intervalos entre as semanas que eles tocam.

    Quando um intervalo atravessa a divisao entre duas semanas, apenas as
    horas efetivamente contidas em cada semana sao contabilizadas nela
    (secao 4.1).
    """

    acumulado: dict[datetime, float] = {}
    for inicio, fim in intervalos:
        inicio = para_utc_naive(inicio)
        fim = para_utc_naive(fim)
        if fim <= inicio:
            continue
        for semana in semanas_do_intervalo(inicio, fim):
            fatia = intersecao(inicio, fim, semana, semana + UMA_SEMANA)
            if fatia is None:
                continue
            horas = duracao_horas(fatia[0], fatia[1])
            acumulado[semana] = acumulado.get(semana, 0.0) + horas
    return acumulado


# --- Dias civis -----------------------------------------------------------


def dias_cobertos(inicio: datetime, fim: datetime) -> set[date]:
    """Dias UTC nos quais ``[inicio, fim)`` tem duracao positiva.

    Um plantao que atravessa a meia-noite conta nos dois dias, desde que
    possua duracao positiva em ambos (secao 4.1).
    """

    inicio = para_utc_naive(inicio)
    fim = para_utc_naive(fim)
    if fim <= inicio:
        return set()
    dias: set[date] = set()
    cursor = datetime(inicio.year, inicio.month, inicio.day)
    while cursor < fim:
        proximo = cursor + UM_DIA
        if intersecao(inicio, fim, cursor, proximo) is not None:
            dias.add(cursor.date())
        cursor = proximo
    return dias


def maior_sequencia_de_dias(dias: set[date]) -> int:
    """Tamanho da maior sequencia de dias civis consecutivos no conjunto."""

    if not dias:
        return 0
    ordenados = sorted(dias)
    melhor = 1
    atual = 1
    for anterior, seguinte in zip(ordenados, ordenados[1:]):
        if seguinte - anterior == UM_DIA:
            atual += 1
        else:
            atual = 1
        melhor = max(melhor, atual)
    return melhor
