"""Utilitarios temporais.

Todas as datas trafegam em UTC. Internamente sao armazenadas como
``datetime`` ingenuos (sem ``tzinfo``) ja convertidos para UTC, o que mantem
as comparacoes do SQLite consistentes.

As convencoes da secao 4.1 da especificacao sao implementadas aqui:

* intervalos sao semiabertos ``[inicio, fim)``;
* a semana comeca na segunda-feira as 00:00 UTC;
* um plantao que atravessa a divisao de semanas tem suas horas repartidas.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc

SEGUNDOS_POR_HORA = 3600

#: Intervalo minimo entre plantoes consecutivos (INV2).
INTERVALO_MINIMO_SEGUNDOS = 11 * SEGUNDOS_POR_HORA

#: Teto semanal de horas confirmadas (INV3).
LIMITE_SEMANAL_SEGUNDOS = 44 * SEGUNDOS_POR_HORA

#: Numero maximo de dias civis consecutivos trabalhados (INV7).
MAXIMO_DIAS_CONSECUTIVOS = 6

#: Duracao minima e maxima de um turno (secao 3).
DURACAO_MINIMA_SEGUNDOS = 4 * SEGUNDOS_POR_HORA
DURACAO_MAXIMA_SEGUNDOS = 12 * SEGUNDOS_POR_HORA

Intervalo = tuple[datetime, datetime]


def agora_utc() -> datetime:
    """Instante atual em UTC, ingenuo, pronto para persistencia."""

    return datetime.now(UTC).replace(tzinfo=None)


def normalizar(momento: datetime) -> datetime:
    """Converte um ``datetime`` para UTC ingenuo.

    Valores sem fuso sao considerados ja expressos em UTC.
    """

    if momento.tzinfo is None:
        return momento
    return momento.astimezone(UTC).replace(tzinfo=None)


def com_fuso(momento: datetime | None) -> datetime | None:
    """Anexa o fuso UTC a um ``datetime`` ingenuo vindo do banco."""

    if momento is None:
        return None
    if momento.tzinfo is None:
        return momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC)


def duracao_segundos(inicio: datetime, fim: datetime) -> int:
    """Duracao, em segundos, do intervalo semiaberto ``[inicio, fim)``."""

    return int((fim - inicio).total_seconds())


def horas(segundos: int | float) -> float:
    """Converte segundos em horas, arredondando para duas casas."""

    return round(segundos / SEGUNDOS_POR_HORA, 2)


def ha_sobreposicao(a: Intervalo, b: Intervalo) -> bool:
    """Indica se dois intervalos semiabertos possuem periodo em comum.

    Intervalos que apenas se tocam (``a.fim == b.inicio``) nao se sobrepoem.
    """

    return a[0] < b[1] and b[0] < a[1]


def inicio_semana(momento: datetime) -> datetime:
    """Segunda-feira, 00:00 UTC, da semana que contem ``momento``."""

    dia = momento.date() - timedelta(days=momento.weekday())
    return datetime(dia.year, dia.month, dia.day)


def segundos_por_semana(intervalos: list[Intervalo]) -> dict[datetime, int]:
    """Distribui a duracao dos intervalos entre as semanas que eles tocam.

    Retorna um mapa ``inicio_da_semana -> segundos`` contabilizando apenas a
    parcela de cada intervalo efetivamente contida na semana.
    """

    acumulado: dict[datetime, int] = defaultdict(int)
    for inicio, fim in intervalos:
        if fim <= inicio:
            continue
        cursor = inicio
        while cursor < fim:
            semana = inicio_semana(cursor)
            proxima = semana + timedelta(days=7)
            limite = min(proxima, fim)
            acumulado[semana] += duracao_segundos(cursor, limite)
            cursor = limite
    return dict(acumulado)


def dias_cobertos(inicio: datetime, fim: datetime) -> set[date]:
    """Dias civis (UTC) com alguma parcela de duracao positiva no intervalo."""

    dias: set[date] = set()
    if fim <= inicio:
        return dias
    cursor = inicio.date()
    while datetime(cursor.year, cursor.month, cursor.day) < fim:
        dias.add(cursor)
        cursor = cursor + timedelta(days=1)
    return dias


def maior_sequencia_consecutiva(dias: set[date]) -> int:
    """Tamanho da maior sequencia de dias civis consecutivos."""

    if not dias:
        return 0
    ordenados = sorted(dias)
    maior = 1
    atual = 1
    for anterior, seguinte in zip(ordenados, ordenados[1:]):
        if (seguinte - anterior).days == 1:
            atual += 1
        else:
            atual = 1
        maior = max(maior, atual)
    return maior


def recorta_periodo(
    intervalo: Intervalo,
    de: datetime | None,
    ate: datetime | None,
) -> bool:
    """Aplica os filtros temporais da secao 4.4 a um intervalo.

    Retorna ``True`` quando o intervalo pertence ao periodo consultado.
    """

    inicio, fim = intervalo
    if de is not None and fim <= de:
        return False
    if ate is not None and inicio >= ate:
        return False
    return True
