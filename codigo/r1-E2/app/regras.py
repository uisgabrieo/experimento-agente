"""Invariantes e regras de negocio (secao 4 da especificacao).

As oito invariantes sao verificadas sobre o estado efetivo do banco. A
estrategia adotada pelos servicos (:mod:`app.servicos`) e:

1. aplicar a mutacao na sessao e fazer ``flush``;
2. revalidar as invariantes dos profissionais afetados;
3. desfazer a transacao inteira caso alguma delas seja violada.

Assim as invariantes valem apos qualquer operacao concluida com sucesso, e
operacoes recusadas nao deixam efeito algum.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable, Sequence

from sqlalchemy.orm import Session

from . import constantes as C
from . import repositorio
from .erros import Conflito
from .modelos import Plantao, Profissional, Substituicao, Turno
from .tempo import (
    dias_trabalhados,
    horas,
    horas_por_semana,
    iso,
    sequencia_excedente,
    sobrepoem,
)

Intervalo = tuple[datetime, datetime]


def intervalos_de(plantoes: Iterable[Plantao]) -> list[Intervalo]:
    """Intervalos ``[data_inicio, data_fim)`` dos turnos dos plantoes."""

    return [(p.turno.data_inicio, p.turno.data_fim) for p in plantoes]


def _confirmados(
    sessao: Session, profissional_id: int
) -> tuple[Sequence[Plantao], list[Intervalo]]:
    plantoes = repositorio.plantoes_confirmados_do_profissional(
        sessao, profissional_id
    )
    return plantoes, intervalos_de(plantoes)


# --- INV1 e INV2 ----------------------------------------------------------
def validar_inv1_inv2(intervalos: Sequence[Intervalo]) -> None:
    """Sobreposicao (INV1) e descanso minimo de 11 horas (INV2).

    Com os intervalos ordenados por inicio, basta comparar pares adjacentes:
    se existe sobreposicao, ela aparece em algum par adjacente; e, na
    ausencia de sobreposicoes, a menor folga tambem esta em um par adjacente.
    """

    ordenados = sorted(intervalos)
    for (ini_a, fim_a), (ini_b, fim_b) in zip(ordenados, ordenados[1:]):
        if sobrepoem(ini_a, fim_a, ini_b, fim_b):
            raise Conflito(
                "INV1: o profissional ja possui plantao confirmado que se "
                f"sobrepoe ao intervalo [{iso(ini_b)}, {iso(fim_b)})"
            )
        folga = horas(ini_b - fim_a)
        if folga < C.DESCANSO_MINIMO_HORAS - C.EPSILON_HORAS:
            raise Conflito(
                f"INV2: intervalo de descanso de {folga:.2f}h entre "
                f"{iso(fim_a)} e {iso(ini_b)} e inferior ao minimo de "
                f"{C.DESCANSO_MINIMO_HORAS:g} horas"
            )


# --- INV3 -----------------------------------------------------------------
def validar_inv3(intervalos: Sequence[Intervalo]) -> None:
    """Teto de 44 horas confirmadas por semana."""

    for semana, total in sorted(horas_por_semana(intervalos).items()):
        if total > C.LIMITE_SEMANAL_HORAS + C.EPSILON_HORAS:
            raise Conflito(
                f"INV3: a semana iniciada em {iso(semana)} totalizaria "
                f"{total:.2f}h, acima do limite de "
                f"{C.LIMITE_SEMANAL_HORAS:g} horas"
            )


# --- INV4 -----------------------------------------------------------------
def validar_inv4(profissional: Profissional, plantoes: Iterable[Plantao]) -> None:
    """Todo plantao confirmado exige a especialidade do turno."""

    possuidas = {e.id for e in profissional.especialidades}
    for plantao in plantoes:
        if plantao.turno.especialidade_id not in possuidas:
            raise Conflito(
                f"INV4: o profissional {profissional.id} nao possui a "
                f"especialidade {plantao.turno.especialidade_id} exigida pelo "
                f"turno {plantao.turno_id}"
            )


# --- INV5 -----------------------------------------------------------------
def validar_inv5(
    sessao: Session, profissional: Profissional, intervalos: Sequence[Intervalo]
) -> None:
    """Plantoes confirmados nao podem coincidir com ausencias."""

    for ausencia in repositorio.ausencias_do_profissional(sessao, profissional.id):
        for inicio, fim in intervalos:
            if sobrepoem(inicio, fim, ausencia.data_inicio, ausencia.data_fim):
                raise Conflito(
                    f"INV5: o intervalo [{iso(inicio)}, {iso(fim)}) se "
                    f"sobrepoe a ausencia {ausencia.id} ({ausencia.tipo}) do "
                    f"profissional {profissional.id}"
                )


# --- INV6 -----------------------------------------------------------------
def validar_inv6(sessao: Session, turno_id: int) -> None:
    """Posicoes da fila ``aguardando`` formam 1, 2, 3, ... sem lacunas."""

    fila = repositorio.fila_aguardando(sessao, turno_id)
    obtidas = [s.posicao for s in fila]
    if obtidas != list(range(1, len(fila) + 1)):
        raise Conflito(
            f"INV6: a fila de substituicao do turno {turno_id} possui "
            f"posicoes invalidas {obtidas}"
        )


# --- INV7 -----------------------------------------------------------------
def validar_inv7(intervalos: Sequence[Intervalo]) -> None:
    """No maximo seis dias civis consecutivos trabalhados."""

    excedente = sequencia_excedente(
        dias_trabalhados(intervalos), C.MAX_DIAS_CONSECUTIVOS
    )
    if excedente:
        raise Conflito(
            f"INV7: a alocacao resultaria em {len(excedente)} dias "
            f"consecutivos de plantao ({excedente[0].isoformat()} a "
            f"{excedente[-1].isoformat()}), acima do maximo de "
            f"{C.MAX_DIAS_CONSECUTIVOS} dias"
        )


# --- INV8 -----------------------------------------------------------------
def calcular_horas_extras(
    carga_semanal: int, intervalos: Sequence[Intervalo]
) -> float:
    """Soma, em todas as semanas, das horas acima da carga semanal."""

    total = 0.0
    for horas_semana in horas_por_semana(intervalos).values():
        excedente = horas_semana - float(carga_semanal)
        if excedente > 0:
            total += excedente
    return round(total, 2)


def recalcular_horas_extras(sessao: Session, profissional: Profissional) -> float:
    """Reaplica INV8 ao profissional, persistindo o valor recalculado."""

    _, intervalos = _confirmados(sessao, profissional.id)
    valor = calcular_horas_extras(profissional.carga_semanal, intervalos)
    profissional.horas_extras = Decimal(f"{valor:.2f}")
    sessao.flush()
    return valor


def validar_inv8(sessao: Session, profissional: Profissional) -> None:
    """Confere a consistencia de ``horas_extras`` (uso defensivo)."""

    _, intervalos = _confirmados(sessao, profissional.id)
    esperado = calcular_horas_extras(profissional.carga_semanal, intervalos)
    atual = float(profissional.horas_extras or 0)
    if abs(atual - esperado) > 0.01:
        raise Conflito(
            f"INV8: horas_extras do profissional {profissional.id} esta em "
            f"{atual:.2f}, mas deveria ser {esperado:.2f}"
        )


# --- Validacao agregada ---------------------------------------------------
def validar_profissional(sessao: Session, profissional: Profissional) -> None:
    """Revalida INV1, INV2, INV3, INV4, INV5 e INV7 para um profissional.

    Deve ser chamada apos ``flush``, para que o estado observado inclua a
    mutacao em avaliacao.
    """

    plantoes, intervalos = _confirmados(sessao, profissional.id)
    validar_inv4(profissional, plantoes)
    validar_inv1_inv2(intervalos)
    validar_inv3(intervalos)
    validar_inv5(sessao, profissional, intervalos)
    validar_inv7(intervalos)


def validar_profissionais(
    sessao: Session, profissionais: Iterable[Profissional]
) -> None:
    """Revalida as invariantes de varios profissionais (usado nas trocas)."""

    for profissional in profissionais:
        validar_profissional(sessao, profissional)


# --- Verificacoes previas -------------------------------------------------
def exigir_profissional_ativo(profissional: Profissional) -> None:
    """RF20 - profissional inativo nao recebe novo plantao."""

    if not profissional.ativo:
        raise Conflito(
            f"o profissional {profissional.id} esta inativo e nao pode "
            "receber novos plantoes"
        )


def exigir_especialidade(profissional: Profissional, turno: Turno) -> None:
    """RF14 / RF32 - o profissional precisa da especialidade do turno."""

    if not profissional.tem_especialidade(turno.especialidade_id):
        raise Conflito(
            f"INV4: o profissional {profissional.id} nao possui a "
            f"especialidade {turno.especialidade_id} exigida pelo turno "
            f"{turno.id}"
        )


def exigir_nao_duplicado(sessao: Session, turno: Turno, profissional_id: int) -> None:
    """RF21 - um profissional nao pode ser alocado duas vezes no turno."""

    if repositorio.profissional_ja_alocado(sessao, turno.id, profissional_id):
        raise Conflito(
            f"o profissional {profissional_id} ja possui plantao confirmado "
            f"no turno {turno.id}"
        )


# --- Fila de substituicao (INV6) ------------------------------------------
def proxima_posicao(sessao: Session, turno_id: int) -> int:
    """Ultima posicao existente na fila ``aguardando`` acrescida de 1."""

    fila = repositorio.fila_aguardando(sessao, turno_id)
    return max((s.posicao for s in fila), default=0) + 1


def reindexar_fila(sessao: Session, turno_id: int) -> None:
    """Renumera a fila ``aguardando`` como 1, 2, 3, ... preservando a ordem."""

    for indice, substituicao in enumerate(
        repositorio.fila_aguardando(sessao, turno_id), start=1
    ):
        if substituicao.posicao != indice:
            substituicao.posicao = indice
    sessao.flush()


def convocar_proximo(sessao: Session, turno: Turno) -> Substituicao | None:
    """Convoca a substituicao de posicao 1 quando a cobertura cai.

    Usada pelo cancelamento de plantao (RF22). As demais substituicoes em
    estado ``aguardando`` tem suas posicoes reduzidas em uma unidade, o que
    preserva INV6.
    """

    if repositorio.cobertura_atual(sessao, turno.id) >= turno.cobertura_minima:
        return None
    fila = repositorio.fila_aguardando(sessao, turno.id)
    if not fila:
        return None
    primeiro = fila[0]
    primeiro.estado = C.SUB_CONVOCADO
    sessao.flush()
    reindexar_fila(sessao, turno.id)
    return primeiro
