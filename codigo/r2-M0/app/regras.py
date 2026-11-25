"""Motor de invariantes e regras de negocio (secao 4).

O nucleo e :func:`validar_invariantes_do_profissional`, que recebe o conjunto
*hipotetico* de plantoes confirmados de um profissional e verifica INV1,
INV2, INV3, INV4, INV5 e INV7 sobre ele. Trabalhar sobre um cenario (e nao
sobre o estado ja gravado) permite validar antes de persistir e, sobretudo,
aprovar uma troca de forma atomica (RF25).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .estados import (
    PLANTAO_CONFIRMADO,
    SUBSTITUICAO_AGUARDANDO,
    SUBSTITUICAO_CONVOCADO,
)
from .models import Ausencia, Plantao, Profissional, Substituicao, Turno
from .tempo import (
    DESCANSO_MINIMO,
    LIMITE_HORAS_SEMANAIS,
    MAX_DIAS_CONSECUTIVOS,
    EPSILON_HORAS,
    dias_cobertos,
    duracao_horas,
    horas_por_semana,
    intervalos_sobrepoem,
    maior_sequencia_de_dias,
    para_utc_naive,
)

# --- Representacao de um cenario -----------------------------------------


@dataclass(frozen=True)
class Alocacao:
    """Um plantao confirmado hipotetico, reduzido ao que as invariantes usam."""

    plantao_id: int | None
    turno_id: int
    data_inicio: datetime
    data_fim: datetime
    especialidade_id: int

    @property
    def dias(self) -> set[date]:
        return dias_cobertos(self.data_inicio, self.data_fim)


def alocacao_de_turno(turno: Turno, plantao_id: int | None = None) -> Alocacao:
    """Constroi uma :class:`Alocacao` a partir de um turno."""

    return Alocacao(
        plantao_id=plantao_id,
        turno_id=turno.id,
        data_inicio=para_utc_naive(turno.data_inicio),
        data_fim=para_utc_naive(turno.data_fim),
        especialidade_id=turno.especialidade_id,
    )


def alocacoes_confirmadas(
    sessao: Session,
    profissional_id: int,
    excluir_plantoes: set[int] | None = None,
) -> list[Alocacao]:
    """Plantoes ``confirmado`` do profissional, como lista de alocacoes."""

    excluir = excluir_plantoes or set()
    consulta = (
        select(Plantao, Turno)
        .join(Turno, Turno.id == Plantao.turno_id)
        .where(
            Plantao.profissional_id == profissional_id,
            Plantao.estado == PLANTAO_CONFIRMADO,
        )
    )
    alocacoes: list[Alocacao] = []
    for plantao, turno in sessao.execute(consulta).all():
        if plantao.id in excluir:
            continue
        alocacoes.append(alocacao_de_turno(turno, plantao.id))
    return alocacoes


def _ausencias_de(sessao: Session, profissional_id: int) -> list[Ausencia]:
    return list(
        sessao.scalars(
            select(Ausencia).where(Ausencia.profissional_id == profissional_id)
        ).all()
    )


# --- Invariantes ----------------------------------------------------------


def _verificar_inv1_e_inv2(alocacoes: list[Alocacao]) -> str | None:
    """INV1 (sem sobreposicao) e INV2 (descanso de 11 horas)."""

    ordenadas = sorted(alocacoes, key=lambda a: (a.data_inicio, a.data_fim))
    for anterior, seguinte in zip(ordenadas, ordenadas[1:]):
        if anterior.data_fim > seguinte.data_inicio:
            return (
                "INV1: plantoes confirmados sobrepostos "
                f"(turnos {anterior.turno_id} e {seguinte.turno_id})"
            )
        if seguinte.data_inicio - anterior.data_fim < DESCANSO_MINIMO:
            intervalo = duracao_horas(anterior.data_fim, seguinte.data_inicio)
            return (
                "INV2: intervalo de descanso inferior a 11 horas entre os turnos "
                f"{anterior.turno_id} e {seguinte.turno_id} ({intervalo:.2f}h)"
            )
    return None


def _verificar_inv3(alocacoes: list[Alocacao]) -> str | None:
    """INV3: no maximo 44 horas confirmadas em qualquer semana."""

    for semana, horas in sorted(horas_por_semana(_intervalos(alocacoes)).items()):
        if horas > LIMITE_HORAS_SEMANAIS + EPSILON_HORAS:
            return (
                "INV3: limite de 44 horas semanais excedido na semana de "
                f"{semana.date().isoformat()} ({horas:.2f}h)"
            )
    return None


def _verificar_inv4(
    alocacoes: list[Alocacao], especialidades: set[int]
) -> str | None:
    """INV4: o profissional precisa ter a especialidade exigida pelo turno."""

    for alocacao in alocacoes:
        if alocacao.especialidade_id not in especialidades:
            return (
                "INV4: profissional nao possui a especialidade "
                f"{alocacao.especialidade_id} exigida pelo turno "
                f"{alocacao.turno_id}"
            )
    return None


def _verificar_inv5(
    alocacoes: list[Alocacao], ausencias: list[Ausencia]
) -> str | None:
    """INV5: plantao confirmado nao pode cair dentro de uma ausencia."""

    for alocacao in alocacoes:
        for ausencia in ausencias:
            if intervalos_sobrepoem(
                alocacao.data_inicio,
                alocacao.data_fim,
                ausencia.data_inicio,
                ausencia.data_fim,
            ):
                return (
                    f"INV5: turno {alocacao.turno_id} sobrepoe a ausencia "
                    f"{ausencia.id} ({ausencia.tipo})"
                )
    return None


def _verificar_inv7(alocacoes: list[Alocacao]) -> str | None:
    """INV7: no maximo seis dias civis consecutivos trabalhados."""

    dias: set[date] = set()
    for alocacao in alocacoes:
        dias |= alocacao.dias
    sequencia = maior_sequencia_de_dias(dias)
    if sequencia > MAX_DIAS_CONSECUTIVOS:
        return (
            "INV7: sequencia de "
            f"{sequencia} dias consecutivos de plantao excede o maximo de "
            f"{MAX_DIAS_CONSECUTIVOS}"
        )
    return None


def _intervalos(alocacoes: list[Alocacao]) -> list[tuple[datetime, datetime]]:
    return [(a.data_inicio, a.data_fim) for a in alocacoes]


def validar_invariantes_do_profissional(
    sessao: Session,
    profissional: Profissional,
    alocacoes: list[Alocacao],
    ausencias: list[Ausencia] | None = None,
) -> str | None:
    """Valida INV1, INV2, INV3, INV4, INV5 e INV7 para um cenario.

    Devolve ``None`` quando o cenario e valido ou uma mensagem descrevendo a
    primeira invariante violada.
    """

    if ausencias is None:
        ausencias = _ausencias_de(sessao, profissional.id)
    especialidades = set(profissional.especialidade_ids)

    for verificacao in (
        lambda: _verificar_inv4(alocacoes, especialidades),
        lambda: _verificar_inv1_e_inv2(alocacoes),
        lambda: _verificar_inv5(alocacoes, ausencias),
        lambda: _verificar_inv3(alocacoes),
        lambda: _verificar_inv7(alocacoes),
    ):
        problema = verificacao()
        if problema is not None:
            return problema
    return None


# --- Validacao de uma nova alocacao (RF14 a RF21) ------------------------


def validar_nova_alocacao(
    sessao: Session,
    turno: Turno,
    profissional: Profissional,
) -> str | None:
    """Checagens de ``POST /plantoes`` e do aceite de convocacao.

    Cobre RF20 (inativo), RF21 (duplicidade no turno) e, em seguida, todas as
    invariantes aplicaveis ao cenario resultante.
    """

    if not profissional.ativo:
        return f"profissional {profissional.id} esta inativo"

    ja_alocado = sessao.scalar(
        select(Plantao.id).where(
            Plantao.turno_id == turno.id,
            Plantao.profissional_id == profissional.id,
            Plantao.estado == PLANTAO_CONFIRMADO,
        )
    )
    if ja_alocado is not None:
        return (
            f"profissional {profissional.id} ja possui plantao confirmado "
            f"no turno {turno.id}"
        )

    cenario = alocacoes_confirmadas(sessao, profissional.id)
    cenario.append(alocacao_de_turno(turno))
    return validar_invariantes_do_profissional(sessao, profissional, cenario)


def cobertura_atual(sessao: Session, turno_id: int) -> int:
    """Quantidade de plantoes ``confirmado`` associados ao turno.

    A cobertura minima e meta operacional, nao invariante (secao 4.2); este
    numero e usado apenas por RF22 e RF31.
    """

    return len(
        sessao.execute(
            select(Plantao.id).where(
                Plantao.turno_id == turno_id,
                Plantao.estado == PLANTAO_CONFIRMADO,
            )
        ).all()
    )


def conflitos_de_especialidade(
    sessao: Session, profissional_id: int, especialidade_id: int
) -> int:
    """Quantos plantoes confirmados dependem do vinculo de especialidade.

    Usado por RF07: o vinculo nao pode ser removido enquanto houver plantao
    confirmado em turno que exija a especialidade, sob pena de violar INV4.
    """

    consulta = (
        select(Plantao.id)
        .join(Turno, Turno.id == Plantao.turno_id)
        .where(
            Plantao.profissional_id == profissional_id,
            Plantao.estado == PLANTAO_CONFIRMADO,
            Turno.especialidade_id == especialidade_id,
        )
    )
    return len(sessao.execute(consulta).all())


# --- INV8: horas extras ---------------------------------------------------


def horas_extras_de(sessao: Session, profissional: Profissional) -> float:
    """Horas extras do profissional conforme a secao 4.3.

    ``soma(max(0, horas_confirmadas_na_semana - carga_semanal))`` sobre todas
    as semanas registradas.
    """

    alocacoes = alocacoes_confirmadas(sessao, profissional.id)
    total = 0.0
    for horas in horas_por_semana(_intervalos(alocacoes)).values():
        excedente = horas - float(profissional.carga_semanal)
        if excedente > 0:
            total += excedente
    return round(total, 2)


def recalcular_horas_extras(sessao: Session, *profissionais: Profissional) -> None:
    """Reescreve ``horas_extras`` para manter INV8 apos qualquer operacao."""

    vistos: set[int] = set()
    for profissional in profissionais:
        if profissional is None or profissional.id in vistos:
            continue
        vistos.add(profissional.id)
        profissional.horas_extras = horas_extras_de(sessao, profissional)
    sessao.flush()


# --- INV6: fila de substituicoes -----------------------------------------


def fila_aguardando(sessao: Session, turno_id: int) -> list[Substituicao]:
    """Substituicoes ``aguardando`` do turno, ordenadas por posicao."""

    return list(
        sessao.scalars(
            select(Substituicao)
            .where(
                Substituicao.turno_id == turno_id,
                Substituicao.estado == SUBSTITUICAO_AGUARDANDO,
            )
            .order_by(Substituicao.posicao, Substituicao.id)
        ).all()
    )


def proxima_posicao(sessao: Session, turno_id: int) -> int:
    """Ultima posicao da fila do turno, acrescida de 1 (RF30)."""

    fila = fila_aguardando(sessao, turno_id)
    return len(fila) + 1


def renumerar_fila(sessao: Session, turno_id: int) -> None:
    """Reatribui 1..n as substituicoes ``aguardando``, preservando INV6."""

    fila = fila_aguardando(sessao, turno_id)
    for indice, substituicao in enumerate(fila, start=1):
        if substituicao.posicao != indice:
            substituicao.posicao = indice
    sessao.flush()


def promover_fila_se_necessario(sessao: Session, turno: Turno) -> Substituicao | None:
    """Convoca a posicao 1 quando a cobertura cai abaixo do minimo (RF22).

    As demais substituicoes ``aguardando`` tem a posicao reduzida em uma
    unidade, o que mantem a sequencia contigua exigida por INV6.
    """

    sessao.flush()
    cobertura = cobertura_atual(sessao, turno.id)
    if cobertura >= turno.cobertura_minima:
        return None

    fila = fila_aguardando(sessao, turno.id)
    if not fila:
        return None

    convocado = fila[0]
    convocado.estado = SUBSTITUICAO_CONVOCADO
    for restante in fila[1:]:
        restante.posicao -= 1
    sessao.flush()
    renumerar_fila(sessao, turno.id)
    return convocado
