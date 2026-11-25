"""Servicos de aplicacao: operacoes que mudam o estado do sistema.

Cada servico aplica suas verificacoes previas, grava a mutacao, revalida as
invariantes afetadas e confirma a transacao. Qualquer violacao desfaz a
transacao por completo (``rollback``), de modo que operacoes recusadas nao
produzem efeito parcial — exigencia explicita de RF25 e RF34.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import constantes as C
from . import regras, repositorio
from .erros import Conflito, ErroDeNegocio
from .modelos import (
    Ausencia,
    Especialidade,
    Plantao,
    Profissional,
    Substituicao,
    Troca,
    Turno,
)
from .tempo import agora, sobrepoem


@contextmanager
def transacao(sessao: Session) -> Iterator[None]:
    """Confirma a transacao no fim do bloco; desfaz tudo em caso de recusa."""

    try:
        yield
        sessao.commit()
    except ErroDeNegocio:
        sessao.rollback()
        raise


def _novo_plantao(turno: Turno, profissional: Profissional) -> Plantao:
    return Plantao(
        turno_id=turno.id,
        profissional_id=profissional.id,
        estado=C.PLANTAO_CONFIRMADO,
    )


# --- Plantoes -------------------------------------------------------------
def alocar_plantao(
    sessao: Session, turno: Turno, profissional: Profissional
) -> Plantao:
    """RF13 - cria um plantao confirmado respeitando RF14 a RF21."""

    with transacao(sessao):
        regras.exigir_profissional_ativo(profissional)  # RF20
        regras.exigir_especialidade(profissional, turno)  # RF14 / INV4
        regras.exigir_nao_duplicado(sessao, turno, profissional.id)  # RF21

        plantao = _novo_plantao(turno, profissional)
        sessao.add(plantao)
        sessao.flush()

        # INV1, INV2, INV3, INV4, INV5 e INV7 (RF15 a RF19) e, depois, INV8.
        regras.validar_profissional(sessao, profissional)
        regras.recalcular_horas_extras(sessao, profissional)
    return plantao


def cancelar_plantao(sessao: Session, plantao: Plantao) -> Plantao:
    """RF22 - cancela o plantao, trata trocas pendentes e a fila do turno."""

    with transacao(sessao):
        if plantao.estado != C.PLANTAO_CANCELADO:
            turno = plantao.turno
            profissional = repositorio.obter_profissional(
                sessao, plantao.profissional_id
            )
            plantao.estado = C.PLANTAO_CANCELADO
            sessao.flush()

            # RF28 - trocas pendentes envolvendo o plantao sao rejeitadas.
            pendentes = repositorio.trocas_do_plantao(
                sessao, plantao.id, C.TROCA_SOLICITADA
            )
            for troca in pendentes:
                troca.estado = C.TROCA_REJEITADA
                troca.data_decisao = agora()
            sessao.flush()

            # RF22 - convocacao da fila quando a cobertura minima e perdida.
            regras.convocar_proximo(sessao, turno)
            # INV8 - as horas canceladas deixam de ser contabilizadas.
            regras.recalcular_horas_extras(sessao, profissional)
            # INV6 - a fila permanece contigua.
            regras.validar_inv6(sessao, turno.id)
    return plantao


# --- Trocas ---------------------------------------------------------------
def _exigir_troca_pendente(troca: Troca) -> None:
    """RF27 - uma troca ja decidida nao recebe nova decisao."""

    if troca.estado != C.TROCA_SOLICITADA:
        raise Conflito(
            f"a troca {troca.id} ja foi decidida (estado '{troca.estado}') e "
            "nao pode receber nova decisao"
        )


def solicitar_troca(sessao: Session, origem: Plantao, destino: Plantao) -> Troca:
    """RF24 - registra uma solicitacao de troca em estado ``solicitada``."""

    with transacao(sessao):
        if origem.id == destino.id:
            raise Conflito(
                "plantao_origem_id e plantao_destino_id devem ser distintos"
            )
        for plantao in (origem, destino):
            if plantao.estado != C.PLANTAO_CONFIRMADO:
                raise Conflito(
                    f"o plantao {plantao.id} nao esta em estado "
                    f"'{C.PLANTAO_CONFIRMADO}'"
                )
        if origem.profissional_id == destino.profissional_id:
            raise Conflito(
                "os plantoes da troca devem pertencer a profissionais diferentes"
            )

        troca = Troca(
            plantao_origem_id=origem.id,
            plantao_destino_id=destino.id,
            estado=C.TROCA_SOLICITADA,
            data_solicitacao=agora(),
        )
        sessao.add(troca)
    return troca


def aprovar_troca(sessao: Session, troca: Troca) -> Troca:
    """RF25 - permuta os profissionais dos dois plantoes, de forma atomica."""

    with transacao(sessao):
        _exigir_troca_pendente(troca)
        origem = repositorio.obter_plantao(sessao, troca.plantao_origem_id)
        destino = repositorio.obter_plantao(sessao, troca.plantao_destino_id)

        for plantao in (origem, destino):
            if plantao.estado != C.PLANTAO_CONFIRMADO:
                raise Conflito(
                    f"o plantao {plantao.id} nao esta confirmado e a troca nao "
                    "pode ser aprovada"
                )

        prof_origem = repositorio.obter_profissional(sessao, origem.profissional_id)
        prof_destino = repositorio.obter_profissional(sessao, destino.profissional_id)

        origem.profissional_id = prof_destino.id
        destino.profissional_id = prof_origem.id
        sessao.flush()

        # INV1, INV2, INV3, INV4, INV5 e INV7 para ambos os profissionais.
        regras.validar_profissionais(sessao, (prof_origem, prof_destino))

        troca.estado = C.TROCA_APROVADA
        troca.data_decisao = agora()

        regras.recalcular_horas_extras(sessao, prof_origem)  # INV8
        regras.recalcular_horas_extras(sessao, prof_destino)
    return troca


def rejeitar_troca(sessao: Session, troca: Troca) -> Troca:
    """RF26 - registra a rejeicao da troca."""

    with transacao(sessao):
        _exigir_troca_pendente(troca)
        troca.estado = C.TROCA_REJEITADA
        troca.data_decisao = agora()
    return troca


# --- Substituicoes --------------------------------------------------------
def inscrever_substituicao(
    sessao: Session, turno: Turno, profissional: Profissional
) -> Substituicao:
    """RF30 - entra na fila de substituicao do turno."""

    with transacao(sessao):
        # RF31 - a fila so existe enquanto falta cobertura.
        cobertura = repositorio.cobertura_atual(sessao, turno.id)
        if cobertura >= turno.cobertura_minima:
            raise Conflito(
                f"o turno {turno.id} ja atende a cobertura minima "
                f"({cobertura}/{turno.cobertura_minima}); nao ha necessidade "
                "de substituicao"
            )
        regras.exigir_especialidade(profissional, turno)  # RF32

        substituicao = Substituicao(
            turno_id=turno.id,
            profissional_id=profissional.id,
            posicao=regras.proxima_posicao(sessao, turno.id),
            estado=C.SUB_AGUARDANDO,
        )
        sessao.add(substituicao)
        sessao.flush()
        regras.validar_inv6(sessao, turno.id)
    return substituicao


def cancelar_substituicao(
    sessao: Session, substituicao: Substituicao
) -> Substituicao:
    """RF33 - sai da fila, reindexando as posicoes posteriores (INV6)."""

    with transacao(sessao):
        if substituicao.estado != C.SUB_AGUARDANDO:
            raise Conflito(
                f"a substituicao {substituicao.id} esta em estado "
                f"'{substituicao.estado}' e nao pode ser cancelada"
            )
        turno_id = substituicao.turno_id
        substituicao.estado = C.SUB_CANCELADA
        sessao.flush()

        regras.reindexar_fila(sessao, turno_id)
        regras.validar_inv6(sessao, turno_id)
    return substituicao


def aceitar_convocacao(sessao: Session, substituicao: Substituicao) -> Plantao:
    """RF34 - aceita a convocacao e cria o plantao correspondente."""

    with transacao(sessao):
        if substituicao.estado != C.SUB_CONVOCADO:
            raise Conflito(
                f"a substituicao {substituicao.id} esta em estado "
                f"'{substituicao.estado}'; o aceite exige o estado "
                f"'{C.SUB_CONVOCADO}'"
            )

        turno = repositorio.obter_turno(sessao, substituicao.turno_id)
        profissional = repositorio.obter_profissional(
            sessao, substituicao.profissional_id
        )

        # Mesmas validacoes de RF14 a RF21.
        regras.exigir_profissional_ativo(profissional)
        regras.exigir_especialidade(profissional, turno)
        regras.exigir_nao_duplicado(sessao, turno, profissional.id)

        plantao = _novo_plantao(turno, profissional)
        sessao.add(plantao)
        sessao.flush()
        regras.validar_profissional(sessao, profissional)

        substituicao.estado = C.SUB_ATENDIDA
        sessao.flush()

        regras.reindexar_fila(sessao, turno.id)
        regras.recalcular_horas_extras(sessao, profissional)
        regras.validar_inv6(sessao, turno.id)
    return plantao


# --- Ausencias ------------------------------------------------------------
def registrar_ausencia(
    sessao: Session,
    profissional: Profissional,
    data_inicio: datetime,
    data_fim: datetime,
    tipo: str,
) -> Ausencia:
    """RF35 - registra a ausencia apenas se nao houver plantao confirmado."""

    with transacao(sessao):
        for plantao in repositorio.plantoes_confirmados_do_profissional(
            sessao, profissional.id
        ):
            if sobrepoem(
                plantao.turno.data_inicio,
                plantao.turno.data_fim,
                data_inicio,
                data_fim,
            ):
                raise Conflito(
                    f"INV5: o plantao confirmado {plantao.id} se sobrepoe ao "
                    "periodo informado; cancele o plantao antes de registrar "
                    "a ausencia"
                )

        ausencia = Ausencia(
            profissional_id=profissional.id,
            data_inicio=data_inicio,
            data_fim=data_fim,
            tipo=tipo,
        )
        sessao.add(ausencia)
        sessao.flush()
        regras.validar_profissional(sessao, profissional)
    return ausencia


# --- Especialidades do profissional ---------------------------------------
def vincular_especialidade(
    sessao: Session, profissional: Profissional, especialidade: Especialidade
) -> Profissional:
    """RF06 - vincula uma especialidade ao profissional."""

    with transacao(sessao):
        if profissional.tem_especialidade(especialidade.id):
            raise Conflito(
                f"a especialidade {especialidade.id} ja esta vinculada ao "
                f"profissional {profissional.id}"
            )
        profissional.especialidades.append(especialidade)
    return profissional


def desvincular_especialidade(
    sessao: Session, profissional: Profissional, especialidade_id: int
) -> None:
    """RF07 - remove o vinculo, preservando INV4."""

    with transacao(sessao):
        turnos = repositorio.turnos_que_exigem_especialidade(
            sessao, profissional.id, especialidade_id
        )
        if turnos:
            raise Conflito(
                "INV4: existem plantoes confirmados do profissional "
                f"{profissional.id} em turnos que exigem a especialidade "
                f"{especialidade_id} (turnos "
                f"{', '.join(str(t.id) for t in turnos)})"
            )

        for especialidade in list(profissional.especialidades):
            if especialidade.id == especialidade_id:
                profissional.especialidades.remove(especialidade)
        sessao.flush()
        regras.validar_profissional(sessao, profissional)


# --- Turnos ---------------------------------------------------------------
def excluir_turno(sessao: Session, turno: Turno) -> None:
    """RF12 - exclui o turno se nao houver plantao confirmado."""

    with transacao(sessao):
        confirmados = repositorio.cobertura_atual(sessao, turno.id)
        if confirmados > 0:
            raise Conflito(
                f"o turno {turno.id} possui {confirmados} plantao(oes) "
                "confirmado(s) e nao pode ser excluido"
            )

        afetados: dict[int, Profissional] = {}
        for plantao in repositorio.plantoes_do_turno(sessao, turno.id):
            afetados[plantao.profissional_id] = repositorio.obter_profissional(
                sessao, plantao.profissional_id
            )
            for troca in repositorio.trocas_do_plantao(sessao, plantao.id):
                sessao.delete(troca)
            sessao.flush()
            sessao.delete(plantao)

        for substituicao in sessao.scalars(
            select(Substituicao).where(Substituicao.turno_id == turno.id)
        ).all():
            sessao.delete(substituicao)

        sessao.flush()
        sessao.delete(turno)
        sessao.flush()

        for profissional in afetados.values():
            regras.recalcular_horas_extras(sessao, profissional)
