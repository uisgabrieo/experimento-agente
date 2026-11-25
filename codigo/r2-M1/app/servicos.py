"""Servicos de aplicacao: operacoes que coordenam modelos e invariantes.

Os roteadores cuidam de HTTP; aqui ficam as transicoes de estado que precisam
ser consistentes e as consultas com filtros temporais da secao 4.4.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from .erros import Conflito, nao_encontrado
from .estados import (
    PLANTAO_CANCELADO,
    PLANTAO_CONFIRMADO,
    SUBSTITUICAO_ATENDIDA,
    SUBSTITUICAO_CONVOCADO,
    TROCA_APROVADA,
    TROCA_REJEITADA,
    TROCA_SOLICITADA,
)
from .models import Ausencia, Especialidade, Plantao, Profissional, Substituicao, Troca, Turno
from .regras import (
    Alocacao,
    alocacao_de_turno,
    alocacoes_confirmadas,
    promover_fila_se_necessario,
    recalcular_horas_extras,
    validar_invariantes_do_profissional,
    validar_nova_alocacao,
)
from .tempo import agora_utc, duracao_horas, intersecao, para_utc_naive

# --- Buscas com 404 -------------------------------------------------------


def obter_profissional(sessao: Session, profissional_id: int) -> Profissional:
    """Busca um profissional ou levanta 404."""

    registro = sessao.get(Profissional, profissional_id)
    if registro is None:
        raise nao_encontrado("profissional", profissional_id)
    return registro


def obter_especialidade(sessao: Session, especialidade_id: int) -> Especialidade:
    """Busca uma especialidade ou levanta 404."""

    registro = sessao.get(Especialidade, especialidade_id)
    if registro is None:
        raise nao_encontrado("especialidade", especialidade_id)
    return registro


def obter_turno(sessao: Session, turno_id: int) -> Turno:
    """Busca um turno ou levanta 404."""

    registro = sessao.get(Turno, turno_id)
    if registro is None:
        raise nao_encontrado("turno", turno_id)
    return registro


def obter_plantao(sessao: Session, plantao_id: int) -> Plantao:
    """Busca um plantao ou levanta 404."""

    registro = sessao.get(Plantao, plantao_id)
    if registro is None:
        raise nao_encontrado("plantao", plantao_id)
    return registro


def obter_troca(sessao: Session, troca_id: int) -> Troca:
    """Busca uma troca ou levanta 404."""

    registro = sessao.get(Troca, troca_id)
    if registro is None:
        raise nao_encontrado("troca", troca_id)
    return registro


def obter_substituicao(sessao: Session, substituicao_id: int) -> Substituicao:
    """Busca uma substituicao ou levanta 404."""

    registro = sessao.get(Substituicao, substituicao_id)
    if registro is None:
        raise nao_encontrado("substituicao", substituicao_id)
    return registro


# --- Alocacao -------------------------------------------------------------


def criar_plantao(
    sessao: Session, turno: Turno, profissional: Profissional
) -> Plantao:
    """Cria um plantao ``confirmado`` validando RF14 a RF21.

    Qualquer violacao resulta em 409 e nada e persistido.
    """

    problema = validar_nova_alocacao(sessao, turno, profissional)
    if problema is not None:
        raise Conflito(problema)

    plantao = Plantao(
        turno_id=turno.id,
        profissional_id=profissional.id,
        estado=PLANTAO_CONFIRMADO,
    )
    sessao.add(plantao)
    sessao.flush()
    recalcular_horas_extras(sessao, profissional)
    return plantao


def cancelar_plantao(sessao: Session, plantao: Plantao) -> Plantao:
    """Cancela o plantao (RF22) e propaga os efeitos colaterais.

    * trocas pendentes que envolvam o plantao sao rejeitadas (RF28);
    * se a cobertura do turno cair abaixo do minimo, a posicao 1 da fila e
      convocada e as demais sao renumeradas (RF22 / INV6);
    * ``horas_extras`` e recalculado, pois as horas deixam de contar
      (INV3 e INV8).
    """

    if plantao.estado == PLANTAO_CANCELADO:
        return plantao

    plantao.estado = PLANTAO_CANCELADO
    sessao.flush()

    _rejeitar_trocas_pendentes(sessao, plantao)

    turno = sessao.get(Turno, plantao.turno_id)
    if turno is not None:
        promover_fila_se_necessario(sessao, turno)

    profissional = sessao.get(Profissional, plantao.profissional_id)
    if profissional is not None:
        recalcular_horas_extras(sessao, profissional)
    return plantao


def _rejeitar_trocas_pendentes(sessao: Session, plantao: Plantao) -> list[Troca]:
    pendentes = list(
        sessao.scalars(
            select(Troca).where(
                Troca.estado == TROCA_SOLICITADA,
                or_(
                    Troca.plantao_origem_id == plantao.id,
                    Troca.plantao_destino_id == plantao.id,
                ),
            )
        ).all()
    )
    instante = agora_utc()
    for troca in pendentes:
        troca.estado = TROCA_REJEITADA
        troca.data_decisao = instante
    if pendentes:
        sessao.flush()
    return pendentes


# --- Trocas ---------------------------------------------------------------


def _cenario_apos_permuta(
    sessao: Session,
    profissional: Profissional,
    plantao_proprio: Plantao,
    turno_recebido: Turno,
) -> list[Alocacao]:
    """Plantoes confirmados do profissional supondo a permuta aplicada."""

    cenario = alocacoes_confirmadas(
        sessao, profissional.id, excluir_plantoes={plantao_proprio.id}
    )
    cenario.append(alocacao_de_turno(turno_recebido, plantao_proprio.id))
    return cenario


def aprovar_troca(sessao: Session, troca: Troca) -> Troca:
    """Aprova a troca de forma atomica (RF25).

    A permuta so e gravada se INV1, INV2, INV3, INV4, INV5 e INV7
    permanecerem validas para os dois profissionais. Caso contrario nada e
    alterado e a operacao resulta em 409.
    """

    if troca.estado != TROCA_SOLICITADA:
        raise Conflito(
            f"troca {troca.id} ja recebeu decisao (estado atual: {troca.estado})"
        )

    origem = obter_plantao(sessao, troca.plantao_origem_id)
    destino = obter_plantao(sessao, troca.plantao_destino_id)

    for plantao in (origem, destino):
        if plantao.estado != PLANTAO_CONFIRMADO:
            raise Conflito(
                f"plantao {plantao.id} nao esta confirmado "
                f"(estado atual: {plantao.estado})"
            )

    if origem.profissional_id == destino.profissional_id:
        raise Conflito("os plantoes da troca pertencem ao mesmo profissional")

    prof_origem = obter_profissional(sessao, origem.profissional_id)
    prof_destino = obter_profissional(sessao, destino.profissional_id)
    turno_origem = obter_turno(sessao, origem.turno_id)
    turno_destino = obter_turno(sessao, destino.turno_id)

    cenario_origem = _cenario_apos_permuta(sessao, prof_origem, origem, turno_destino)
    cenario_destino = _cenario_apos_permuta(sessao, prof_destino, destino, turno_origem)

    problema = validar_invariantes_do_profissional(
        sessao, prof_origem, cenario_origem
    )
    if problema is not None:
        raise Conflito(f"troca recusada para profissional {prof_origem.id}: {problema}")

    problema = validar_invariantes_do_profissional(
        sessao, prof_destino, cenario_destino
    )
    if problema is not None:
        raise Conflito(
            f"troca recusada para profissional {prof_destino.id}: {problema}"
        )

    # A partir daqui a permuta e segura: aplica tudo de uma vez.
    origem.profissional_id, destino.profissional_id = (
        prof_destino.id,
        prof_origem.id,
    )
    troca.estado = TROCA_APROVADA
    troca.data_decisao = agora_utc()
    sessao.flush()
    recalcular_horas_extras(sessao, prof_origem, prof_destino)
    return troca


def rejeitar_troca(sessao: Session, troca: Troca) -> Troca:
    """Rejeita a troca (RF26), impedindo nova decisao (RF27)."""

    if troca.estado != TROCA_SOLICITADA:
        raise Conflito(
            f"troca {troca.id} ja recebeu decisao (estado atual: {troca.estado})"
        )
    troca.estado = TROCA_REJEITADA
    troca.data_decisao = agora_utc()
    sessao.flush()
    return troca


# --- Substituicoes --------------------------------------------------------


def aceitar_convocacao(
    sessao: Session, substituicao: Substituicao
) -> tuple[Plantao, Substituicao]:
    """Aceita a convocacao (RF34).

    So e permitido no estado ``convocado``. O plantao e criado com as mesmas
    validacoes de RF14 a RF21; se alguma falhar, nenhum plantao e criado e a
    substituicao permanece ``convocado``.
    """

    if substituicao.estado != SUBSTITUICAO_CONVOCADO:
        raise Conflito(
            f"substituicao {substituicao.id} nao esta convocada "
            f"(estado atual: {substituicao.estado})"
        )

    turno = obter_turno(sessao, substituicao.turno_id)
    profissional = obter_profissional(sessao, substituicao.profissional_id)

    plantao = criar_plantao(sessao, turno, profissional)
    substituicao.estado = SUBSTITUICAO_ATENDIDA
    sessao.flush()
    return plantao, substituicao


# --- Consultas com filtro temporal (secao 4.4) ---------------------------


def aplicar_filtro_temporal(
    consulta: Select,
    de: datetime | None,
    ate: datetime | None,
) -> Select:
    """Restringe a consulta aos turnos que se sobrepoem a ``[de, ate)``.

    * apenas ``de``: turnos que terminem depois desse instante;
    * apenas ``ate``: turnos que comecem antes desse instante;
    * ambos: sobreposicao com o periodo semiaberto.
    """

    if de is not None:
        consulta = consulta.where(Turno.data_fim > para_utc_naive(de))
    if ate is not None:
        consulta = consulta.where(Turno.data_inicio < para_utc_naive(ate))
    return consulta


def escala_do_profissional(
    sessao: Session,
    profissional: Profissional,
    de: datetime | None,
    ate: datetime | None,
) -> tuple[list[dict], float]:
    """Itens da escala e horas do periodo (RF23).

    Sao considerados os plantoes ``confirmado`` cujos turnos se sobrepoem ao
    periodo consultado. ``horas_periodo`` soma apenas as horas efetivamente
    contidas em ``[de, ate)``.
    """

    consulta = (
        select(Plantao, Turno)
        .join(Turno, Turno.id == Plantao.turno_id)
        .where(
            Plantao.profissional_id == profissional.id,
            Plantao.estado == PLANTAO_CONFIRMADO,
        )
        .order_by(Turno.data_inicio, Turno.id)
    )
    consulta = aplicar_filtro_temporal(consulta, de, ate)

    itens: list[dict] = []
    horas_periodo = 0.0
    for plantao, turno in sessao.execute(consulta).all():
        inicio = para_utc_naive(turno.data_inicio)
        fim = para_utc_naive(turno.data_fim)
        itens.append(
            {
                "plantao_id": plantao.id,
                "turno_id": turno.id,
                "profissional_id": plantao.profissional_id,
                "estado": plantao.estado,
                "data_inicio": inicio,
                "data_fim": fim,
                "especialidade_id": turno.especialidade_id,
                "horas": round(duracao_horas(inicio, fim), 2),
            }
        )
        horas_periodo += _horas_no_periodo(inicio, fim, de, ate)

    return itens, round(horas_periodo, 2)


def _horas_no_periodo(
    inicio: datetime,
    fim: datetime,
    de: datetime | None,
    ate: datetime | None,
) -> float:
    """Horas do intervalo que caem dentro de ``[de, ate)``."""

    if de is None and ate is None:
        return duracao_horas(inicio, fim)
    janela_inicio = para_utc_naive(de) if de is not None else inicio
    janela_fim = para_utc_naive(ate) if ate is not None else fim
    fatia = intersecao(inicio, fim, janela_inicio, janela_fim)
    if fatia is None:
        return 0.0
    return duracao_horas(fatia[0], fatia[1])


def ausencias_conflitantes(
    sessao: Session,
    profissional_id: int,
    data_inicio: datetime,
    data_fim: datetime,
) -> list[Plantao]:
    """Plantoes confirmados que colidem com uma ausencia a ser criada (RF35)."""

    consulta = (
        select(Plantao, Turno)
        .join(Turno, Turno.id == Plantao.turno_id)
        .where(
            Plantao.profissional_id == profissional_id,
            Plantao.estado == PLANTAO_CONFIRMADO,
            Turno.data_inicio < para_utc_naive(data_fim),
            Turno.data_fim > para_utc_naive(data_inicio),
        )
    )
    return [plantao for plantao, _ in sessao.execute(consulta).all()]


def registrar_ausencia(
    sessao: Session,
    profissional: Profissional,
    data_inicio: datetime,
    data_fim: datetime,
    tipo: str,
) -> Ausencia:
    """Registra a ausencia preservando INV5 (RF35)."""

    conflitos = ausencias_conflitantes(
        sessao, profissional.id, data_inicio, data_fim
    )
    if conflitos:
        ids = ", ".join(str(p.id) for p in conflitos)
        raise Conflito(
            "INV5: existem plantoes confirmados sobrepostos ao periodo "
            f"informado ({ids}); cancele-os antes de registrar a ausencia"
        )

    ausencia = Ausencia(
        profissional_id=profissional.id,
        data_inicio=para_utc_naive(data_inicio),
        data_fim=para_utc_naive(data_fim),
        tipo=tipo,
    )
    sessao.add(ausencia)
    sessao.flush()
    return ausencia
