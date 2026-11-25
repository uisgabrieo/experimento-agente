"""Utilitarios temporais.

Convencoes adotadas (secao 4.1 da especificacao):

* todos os instantes sao tratados em UTC;
* turnos e ausencias sao intervalos semiabertos ``[inicio, fim)``;
* dois intervalos se sobrepoem quando possuem algum periodo em comum, de
  modo que intervalos apenas encostados (``fim_a == inicio_b``) nao se
  sobrepoem;
* a semana comeca na segunda-feira as 00:00 UTC e termina na segunda-feira
  seguinte as 00:00 UTC.

Internamente a aplicacao armazena e manipula ``datetime`` *naive*
interpretados como UTC (o SQLite nao preserva fuso). A conversao para a
fronteira HTTP (aware/UTC) acontece nos esquemas Pydantic.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Sequence

UTC = timezone.utc

UMA_SEMANA = timedelta(days=7)
UM_DIA = timedelta(days=1)


# --- Normalizacao ---------------------------------------------------------
def agora() -> datetime:
    """Instante atual em UTC, *naive* (pronto para persistencia)."""

    return datetime.now(UTC).replace(tzinfo=None)


def para_utc(valor: datetime) -> datetime:
    """Converte um ``datetime`` para UTC *aware*.

    Valores sem fuso sao interpretados como ja estando em UTC.
    """

    if valor.tzinfo is None:
        return valor.replace(tzinfo=UTC)
    return valor.astimezone(UTC)


def para_naive_utc(valor: datetime) -> datetime:
    """Converte um ``datetime`` para UTC e remove o fuso."""

    return para_utc(valor).replace(tzinfo=None)


def iso(valor: datetime | None) -> str | None:
    """Representacao ISO 8601 em UTC, com sufixo ``Z``."""

    if valor is None:
        return None
    return para_utc(valor).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Intervalos -----------------------------------------------------------
def sobrepoem(
    a_inicio: datetime, a_fim: datetime, b_inicio: datetime, b_fim: datetime
) -> bool:
    """Indica se ``[a_inicio, a_fim)`` e ``[b_inicio, b_fim)`` se sobrepoem."""

    return a_inicio < b_fim and b_inicio < a_fim


def interseccao(
    a_inicio: datetime, a_fim: datetime, b_inicio: datetime, b_fim: datetime
) -> timedelta:
    """Duracao da interseccao entre dois intervalos semiabertos."""

    inicio = max(a_inicio, b_inicio)
    fim = min(a_fim, b_fim)
    if fim <= inicio:
        return timedelta(0)
    return fim - inicio


def horas(duracao: timedelta) -> float:
    """Converte uma duracao em horas decimais."""

    return duracao.total_seconds() / 3600.0


def duracao_horas(inicio: datetime, fim: datetime) -> float:
    """Duracao de um intervalo, em horas decimais."""

    return horas(fim - inicio)


def horas_interseccao(
    a_inicio: datetime, a_fim: datetime, b_inicio: datetime, b_fim: datetime
) -> float:
    """Horas em comum entre dois intervalos semiabertos."""

    return horas(interseccao(a_inicio, a_fim, b_inicio, b_fim))


# --- Semanas (INV3 / INV8) ------------------------------------------------
def inicio_semana(instante: datetime) -> datetime:
    """Segunda-feira 00:00 UTC da semana a qual o instante pertence."""

    base = instante.replace(hour=0, minute=0, second=0, microsecond=0)
    return base - timedelta(days=base.weekday())


def horas_por_semana(
    intervalos: Iterable[tuple[datetime, datetime]],
) -> dict[datetime, float]:
    """Distribui as horas dos intervalos entre as semanas que eles tocam.

    Quando um intervalo atravessa a divisao entre duas semanas, apenas as
    horas efetivamente contidas em cada semana sao contabilizadas nela.
    """

    acumulado: dict[datetime, float] = defaultdict(float)
    for inicio, fim in intervalos:
        if fim <= inicio:
            continue
        cursor = inicio_semana(inicio)
        while cursor < fim:
            proxima = cursor + UMA_SEMANA
            parcela = horas_interseccao(inicio, fim, cursor, proxima)
            if parcela > 0:
                acumulado[cursor] += parcela
            cursor = proxima
    return dict(acumulado)


# --- Dias civis (INV7) ----------------------------------------------------
def dias_cobertos(inicio: datetime, fim: datetime) -> set[date]:
    """Dias civis (UTC) com alguma parcela de duracao positiva no intervalo."""

    cobertos: set[date] = set()
    if fim <= inicio:
        return cobertos
    cursor = datetime.combine(inicio.date(), time.min)
    while cursor < fim:
        proximo = cursor + UM_DIA
        if interseccao(inicio, fim, cursor, proximo) > timedelta(0):
            cobertos.add(cursor.date())
        cursor = proximo
    return cobertos


def dias_trabalhados(intervalos: Iterable[tuple[datetime, datetime]]) -> set[date]:
    """Uniao dos dias civis cobertos por uma colecao de intervalos."""

    resultado: set[date] = set()
    for inicio, fim in intervalos:
        resultado |= dias_cobertos(inicio, fim)
    return resultado


def sequencia_excedente(dias: Iterable[date], maximo: int) -> list[date]:
    """Primeira sequencia de dias consecutivos maior que ``maximo``.

    Retorna lista vazia quando nenhuma sequencia excede o limite. Util para
    compor mensagens de erro informativas.
    """

    ordenados = sorted(set(dias))
    if not ordenados:
        return []
    corrente: list[date] = [ordenados[0]]
    for anterior, proximo in zip(ordenados, ordenados[1:]):
        if (proximo - anterior).days == 1:
            corrente.append(proximo)
        else:
            if len(corrente) > maximo:
                return corrente
            corrente = [proximo]
    if len(corrente) > maximo:
        return corrente
    return []


# --- Filtros temporais (secao 4.4) ----------------------------------------
def dentro_do_periodo(
    inicio: datetime, fim: datetime, de: datetime | None, ate: datetime | None
) -> bool:
    """Aplica as regras da secao 4.4 a um intervalo ``[inicio, fim)``.

    * ``de`` e limite inicial inclusivo e ``ate`` limite final exclusivo;
    * com ambos informados, considera-se sobreposicao com ``[de, ate)``;
    * so ``de``: intervalos que terminem depois desse instante;
    * so ``ate``: intervalos que comecem antes desse instante.
    """

    if de is not None and fim <= de:
        return False
    if ate is not None and inicio >= ate:
        return False
    return True


def horas_recortadas(
    inicio: datetime, fim: datetime, de: datetime | None, ate: datetime | None
) -> float:
    """Horas de ``[inicio, fim)`` restritas a janela ``[de, ate)``."""

    janela_inicio = inicio if de is None else max(inicio, de)
    janela_fim = fim if ate is None else min(fim, ate)
    if janela_fim <= janela_inicio:
        return 0.0
    return duracao_horas(janela_inicio, janela_fim)


def horas_no_periodo(
    intervalos: Sequence[tuple[datetime, datetime]],
    de: datetime | None,
    ate: datetime | None,
) -> float:
    """Soma das horas dos intervalos restritas a ``[de, ate)``."""

    return float(
        sum(horas_recortadas(inicio, fim, de, ate) for inicio, fim in intervalos)
    )
