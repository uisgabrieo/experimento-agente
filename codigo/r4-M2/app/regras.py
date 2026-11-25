"""Regras de negocio e invariantes (secao 4 da especificacao).

O nucleo deste modulo e :func:`validar_escala`, que recebe o conjunto
*completo* de plantoes confirmados propostos para um profissional e verifica
as invariantes INV1, INV2, INV3, INV4, INV5 e INV7 sobre ele.

Validar o conjunto inteiro, e nao apenas o plantao novo, permite reaproveitar
a mesma funcao tanto na alocacao quanto na aprovacao de trocas, onde a
permuta precisa ser avaliada de forma atomica antes de ser aplicada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date

from app.tempo import (
    INTERVALO_MINIMO_SEGUNDOS,
    LIMITE_SEMANAL_SEGUNDOS,
    MAXIMO_DIAS_CONSECUTIVOS,
    Intervalo,
    dias_cobertos,
    duracao_segundos,
    ha_sobreposicao,
    horas,
    maior_sequencia_consecutiva,
    segundos_por_semana,
)


@dataclass(frozen=True)
class ItemEscala:
    """Plantao confirmado (real ou hipotetico) de um profissional."""

    inicio: datetime
    fim: datetime
    especialidade_id: int
    plantao_id: int | None = None
    turno_id: int | None = None

    @property
    def intervalo(self) -> Intervalo:
        """Intervalo semiaberto ``[inicio, fim)`` do item."""

        return (self.inicio, self.fim)

    @property
    def segundos(self) -> int:
        """Duracao do item, em segundos."""

        return duracao_segundos(self.inicio, self.fim)


@dataclass(frozen=True)
class Violacao:
    """Descricao de uma invariante violada."""

    codigo: str
    mensagem: str

    def __str__(self) -> str:  # pragma: no cover - conveniencia
        return f"{self.codigo}: {self.mensagem}"

    @property
    def detalhe(self) -> str:
        """Texto usado no campo ``detail`` das respostas 409."""

        return f"{self.codigo}: {self.mensagem}"


# ---------------------------------------------------------------------------
# Invariantes individuais
# ---------------------------------------------------------------------------


def verificar_inv4(itens: list[ItemEscala], especialidades: set[int]) -> Violacao | None:
    """INV4 - o profissional precisa ter a especialidade exigida pelo turno."""

    for item in itens:
        if item.especialidade_id not in especialidades:
            return Violacao(
                "INV4",
                "profissional nao possui a especialidade exigida pelo turno",
            )
    return None


def verificar_inv5(itens: list[ItemEscala], ausencias: list[Intervalo]) -> Violacao | None:
    """INV5 - plantao confirmado nao pode cair dentro de uma ausencia."""

    for item in itens:
        for ausencia in ausencias:
            if ha_sobreposicao(item.intervalo, ausencia):
                return Violacao(
                    "INV5",
                    "plantao se sobrepoe a um periodo de ausencia do profissional",
                )
    return None


def verificar_inv1(itens: list[ItemEscala]) -> Violacao | None:
    """INV1 - plantoes confirmados do mesmo profissional nao se sobrepoem."""

    ordenados = sorted(itens, key=lambda item: (item.inicio, item.fim))
    for anterior, seguinte in zip(ordenados, ordenados[1:]):
        if ha_sobreposicao(anterior.intervalo, seguinte.intervalo):
            return Violacao(
                "INV1",
                "profissional ja possui plantao confirmado sobreposto a este periodo",
            )
    return None


def verificar_inv2(itens: list[ItemEscala]) -> Violacao | None:
    """INV2 - intervalo minimo de 11 horas entre plantoes consecutivos.

    Supondo o conjunto ja livre de sobreposicoes (INV1), a menor folga entre
    quaisquer dois plantoes ocorre entre vizinhos na ordem cronologica.
    """

    ordenados = sorted(itens, key=lambda item: (item.inicio, item.fim))
    for anterior, seguinte in zip(ordenados, ordenados[1:]):
        folga = duracao_segundos(anterior.fim, seguinte.inicio)
        if folga < INTERVALO_MINIMO_SEGUNDOS:
            return Violacao(
                "INV2",
                "intervalo entre plantoes consecutivos menor que 11 horas",
            )
    return None


def verificar_inv3(itens: list[ItemEscala]) -> Violacao | None:
    """INV3 - no maximo 44 horas confirmadas em qualquer semana."""

    por_semana = segundos_por_semana([item.intervalo for item in itens])
    for semana, segundos in sorted(por_semana.items()):
        if segundos > LIMITE_SEMANAL_SEGUNDOS:
            return Violacao(
                "INV3",
                (
                    "limite de 44 horas semanais excedido na semana iniciada em "
                    f"{semana.date().isoformat()} ({horas(segundos)} horas)"
                ),
            )
    return None


def verificar_inv7(itens: list[ItemEscala]) -> Violacao | None:
    """INV7 - no maximo seis dias civis consecutivos trabalhados."""

    dias: set[date] = set()
    for item in itens:
        dias |= dias_cobertos(item.inicio, item.fim)
    if maior_sequencia_consecutiva(dias) > MAXIMO_DIAS_CONSECUTIVOS:
        return Violacao(
            "INV7",
            "profissional ficaria com plantoes confirmados em mais de seis dias consecutivos",
        )
    return None


# ---------------------------------------------------------------------------
# Validacao agregada
# ---------------------------------------------------------------------------


def validar_escala(
    itens: list[ItemEscala],
    especialidades: set[int],
    ausencias: list[Intervalo],
) -> Violacao | None:
    """Valida o conjunto proposto de plantoes confirmados de um profissional.

    Retorna a primeira violacao encontrada ou ``None`` se o conjunto for
    integralmente valido.
    """

    verificacoes = (
        lambda: verificar_inv4(itens, especialidades),
        lambda: verificar_inv5(itens, ausencias),
        lambda: verificar_inv1(itens),
        lambda: verificar_inv2(itens),
        lambda: verificar_inv3(itens),
        lambda: verificar_inv7(itens),
    )
    for verificacao in verificacoes:
        violacao = verificacao()
        if violacao is not None:
            return violacao
    return None


def calcular_horas_extras(itens: list[ItemEscala], carga_semanal: int) -> float:
    """INV8 - soma, em todas as semanas, das horas alem da carga semanal.

    ``horas_extras = soma(max(0, horas_confirmadas_na_semana - carga_semanal))``
    """

    limite = carga_semanal * 3600
    excedente = 0
    for segundos in segundos_por_semana([item.intervalo for item in itens]).values():
        if segundos > limite:
            excedente += segundos - limite
    return horas(excedente)


def total_horas(itens: list[ItemEscala]) -> float:
    """Soma, em horas, da duracao dos itens informados."""

    return horas(sum(item.segundos for item in itens))


def verificar_inv6(posicoes: list[int]) -> bool:
    """INV6 - posicoes em espera formam a sequencia 1..n sem lacunas."""

    return sorted(posicoes) == list(range(1, len(posicoes) + 1))
