"""Servicos de dominio.

Concentra as operacoes que alteram o estado do sistema, garantindo que as
invariantes da secao 4 continuem validas apos cada uma delas.

Nenhuma funcao deste modulo faz ``commit``: isso cabe as rotas. Assim, uma
excecao levantada no meio de uma operacao descarta todo o trabalho parcial.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models
from app.erros import conflito, nao_encontrado
from app.regras import (
    ItemEscala,
    calcular_horas_extras,
    validar_escala,
)
from app.tempo import Intervalo, agora_utc, ha_sobreposicao


# ---------------------------------------------------------------------------
# Buscas basicas
# ---------------------------------------------------------------------------


def obter_profissional(sessao: Session, profissional_id: int) -> models.Profissional:
    """Busca o profissional ou levanta 404."""

    profissional = sessao.get(models.Profissional, profissional_id)
    if profissional is None:
        raise nao_encontrado("profissional nao encontrado")
    return profissional


def obter_especialidade(sessao: Session, especialidade_id: int) -> models.Especialidade:
    """Busca a especialidade ou levanta 404."""

    especialidade = sessao.get(models.Especialidade, especialidade_id)
    if especialidade is None:
        raise nao_encontrado("especialidade nao encontrada")
    return especialidade


def obter_turno(sessao: Session, turno_id: int) -> models.Turno:
    """Busca o turno ou levanta 404."""

    turno = sessao.get(models.Turno, turno_id)
    if turno is None:
        raise nao_encontrado("turno nao encontrado")
    return turno


def obter_plantao(sessao: Session, plantao_id: int) -> models.Plantao:
    """Busca o plantao ou levanta 404."""

    plantao = sessao.get(models.Plantao, plantao_id)
    if plantao is None:
        raise nao_encontrado("plantao nao encontrado")
    return plantao


def obter_troca(sessao: Session, troca_id: int) -> models.Troca:
    """Busca a troca ou levanta 404."""

    troca = sessao.get(models.Troca, troca_id)
    if troca is None:
        raise nao_encontrado("troca nao encontrada")
    return troca


def obter_substituicao(sessao: Session, substituicao_id: int) -> models.Substituicao:
    """Busca a substituicao ou levanta 404."""

    substituicao = sessao.get(models.Substituicao, substituicao_id)
    if substituicao is None:
        raise nao_encontrado("substituicao nao encontrada")
    return substituicao


# ---------------------------------------------------------------------------
# Coleta de estado para as invariantes
# ---------------------------------------------------------------------------


def itens_confirmados(
    sessao: Session,
    profissional_id: int,
    excluir: set[int] | None = None,
    incluir: list[ItemEscala] | None = None,
) -> list[ItemEscala]:
    """Monta o conjunto de plantoes confirmados de um profissional.

    ``excluir`` remove plantoes por ``id`` (util para simular cancelamentos ou
    permutas) e ``incluir`` adiciona itens hipoteticos ao conjunto.
    """

    excluir = excluir or set()
    consulta = (
        select(models.Plantao, models.Turno)
        .join(models.Turno, models.Turno.id == models.Plantao.turno_id)
        .where(
            models.Plantao.profissional_id == profissional_id,
            models.Plantao.estado == models.ESTADO_PLANTAO_CONFIRMADO,
        )
    )
    itens = [
        ItemEscala(
            inicio=turno.data_inicio,
            fim=turno.data_fim,
            especialidade_id=turno.especialidade_id,
            plantao_id=plantao.id,
            turno_id=turno.id,
        )
        for plantao, turno in sessao.execute(consulta).all()
        if plantao.id not in excluir
    ]
    if incluir:
        itens.extend(incluir)
    return itens


def ausencias_do_profissional(sessao: Session, profissional_id: int) -> list[Intervalo]:
    """Intervalos de ausencia registrados para o profissional."""

    consulta = select(models.Ausencia).where(
        models.Ausencia.profissional_id == profissional_id
    )
    return [
        (ausencia.data_inicio, ausencia.data_fim)
        for ausencia in sessao.execute(consulta).scalars().all()
    ]


def item_do_turno(turno: models.Turno, plantao_id: int | None = None) -> ItemEscala:
    """Converte um turno no item de escala correspondente."""

    return ItemEscala(
        inicio=turno.data_inicio,
        fim=turno.data_fim,
        especialidade_id=turno.especialidade_id,
        plantao_id=plantao_id,
        turno_id=turno.id,
    )


def validar_conjunto(
    sessao: Session,
    profissional: models.Profissional,
    itens: list[ItemEscala],
) -> None:
    """Valida o conjunto proposto e levanta 409 na primeira violacao."""

    violacao = validar_escala(
        itens,
        profissional.especialidade_ids,
        ausencias_do_profissional(sessao, profissional.id),
    )
    if violacao is not None:
        raise conflito(violacao.detalhe)


def recalcular_horas_extras(sessao: Session, profissional: models.Profissional) -> None:
    """INV8 - recalcula ``horas_extras`` a partir dos plantoes confirmados."""

    itens = itens_confirmados(sessao, profissional.id)
    valor = calcular_horas_extras(itens, profissional.carga_semanal)
    profissional.horas_extras = Decimal(str(valor))
    sessao.flush()


# ---------------------------------------------------------------------------
# Cobertura e fila de substituicao
# ---------------------------------------------------------------------------


def contar_confirmados(sessao: Session, turno_id: int) -> int:
    """Quantidade de plantoes confirmados associados ao turno."""

    total = sessao.execute(
        # pylint: disable-next=not-callable
        select(func.count(models.Plantao.id)).where(
            models.Plantao.turno_id == turno_id,
            models.Plantao.estado == models.ESTADO_PLANTAO_CONFIRMADO,
        )
    ).scalar_one()
    return int(total or 0)


def fila_aguardando(sessao: Session, turno_id: int) -> list[models.Substituicao]:
    """Substituicoes em espera do turno, ordenadas por posicao."""

    consulta = (
        select(models.Substituicao)
        .where(
            models.Substituicao.turno_id == turno_id,
            models.Substituicao.estado == models.ESTADO_SUB_AGUARDANDO,
        )
        .order_by(models.Substituicao.posicao, models.Substituicao.id)
    )
    return list(sessao.execute(consulta).scalars().all())


def renumerar_fila(sessao: Session, turno_id: int) -> None:
    """INV6 - reatribui 1..n as substituicoes em espera, sem lacunas."""

    for indice, substituicao in enumerate(fila_aguardando(sessao, turno_id), start=1):
        if substituicao.posicao != indice:
            substituicao.posicao = indice
    sessao.flush()


def promover_fila(sessao: Session, turno: models.Turno) -> None:
    """RF22 - convoca o primeiro da fila quando a cobertura fica deficitaria.

    A substituicao de posicao 1 passa a ``convocado``; ao sair da espera ela
    deixa de ocupar posicao, e :func:`renumerar_fila` reatribui 1..n as
    restantes - o que equivale a reduzir cada uma em uma unidade e preserva
    INV6.
    """

    if contar_confirmados(sessao, turno.id) >= turno.cobertura_minima:
        return
    fila = fila_aguardando(sessao, turno.id)
    if not fila:
        return
    fila[0].estado = models.ESTADO_SUB_CONVOCADO
    sessao.flush()
    renumerar_fila(sessao, turno.id)


# ---------------------------------------------------------------------------
# Alocacao de plantoes
# ---------------------------------------------------------------------------


def alocar_plantao(
    sessao: Session,
    turno: models.Turno,
    profissional: models.Profissional,
) -> models.Plantao:
    """RF13 a RF21 - cria um plantao confirmado validando as invariantes."""

    if not profissional.ativo:
        raise conflito("profissional inativo nao pode receber novos plantoes")

    ja_alocado = sessao.execute(
        select(models.Plantao.id).where(
            models.Plantao.turno_id == turno.id,
            models.Plantao.profissional_id == profissional.id,
            models.Plantao.estado == models.ESTADO_PLANTAO_CONFIRMADO,
        )
    ).first()
    if ja_alocado is not None:
        raise conflito("profissional ja esta alocado neste turno")

    itens = itens_confirmados(sessao, profissional.id, incluir=[item_do_turno(turno)])
    validar_conjunto(sessao, profissional, itens)

    plantao = models.Plantao(
        turno_id=turno.id,
        profissional_id=profissional.id,
        estado=models.ESTADO_PLANTAO_CONFIRMADO,
    )
    sessao.add(plantao)
    sessao.flush()
    recalcular_horas_extras(sessao, profissional)
    return plantao


def cancelar_plantao(sessao: Session, plantao: models.Plantao) -> models.Plantao:
    """RF22 - cancela o plantao e aplica os efeitos colaterais previstos."""

    if plantao.estado == models.ESTADO_PLANTAO_CANCELADO:
        return plantao

    plantao.estado = models.ESTADO_PLANTAO_CANCELADO
    sessao.flush()

    rejeitar_trocas_pendentes(sessao, plantao.id)

    turno = sessao.get(models.Turno, plantao.turno_id)
    if turno is not None:
        promover_fila(sessao, turno)

    profissional = sessao.get(models.Profissional, plantao.profissional_id)
    if profissional is not None:
        recalcular_horas_extras(sessao, profissional)

    sessao.flush()
    return plantao


# ---------------------------------------------------------------------------
# Trocas
# ---------------------------------------------------------------------------


def rejeitar_trocas_pendentes(sessao: Session, plantao_id: int) -> None:
    """RF28 - trocas pendentes de um plantao cancelado sao rejeitadas."""

    consulta = select(models.Troca).where(
        models.Troca.estado == models.ESTADO_TROCA_SOLICITADA,
        or_(
            models.Troca.plantao_origem_id == plantao_id,
            models.Troca.plantao_destino_id == plantao_id,
        ),
    )
    momento = agora_utc()
    for troca in sessao.execute(consulta).scalars().all():
        troca.estado = models.ESTADO_TROCA_REJEITADA
        troca.data_decisao = momento
    sessao.flush()


def solicitar_troca(
    sessao: Session,
    origem: models.Plantao,
    destino: models.Plantao,
) -> models.Troca:
    """RF24 - registra a solicitacao de permuta entre dois plantoes."""

    if origem.id == destino.id:
        raise conflito("os plantoes da troca devem ser distintos")
    if not origem.confirmado or not destino.confirmado:
        raise conflito("ambos os plantoes devem estar em estado confirmado")
    if origem.profissional_id == destino.profissional_id:
        raise conflito("os plantoes devem pertencer a profissionais diferentes")

    troca = models.Troca(
        plantao_origem_id=origem.id,
        plantao_destino_id=destino.id,
        estado=models.ESTADO_TROCA_SOLICITADA,
        data_solicitacao=agora_utc(),
        data_decisao=None,
    )
    sessao.add(troca)
    sessao.flush()
    return troca


def aprovar_troca(sessao: Session, troca: models.Troca) -> models.Troca:
    """RF25 - permuta os profissionais de forma atomica.

    A permuta so e aplicada se o estado resultante mantiver INV1, INV2, INV3,
    INV4, INV5 e INV7 validas para os dois profissionais envolvidos.
    """

    garantir_pendente(troca)

    origem = obter_plantao(sessao, troca.plantao_origem_id)
    destino = obter_plantao(sessao, troca.plantao_destino_id)
    if not origem.confirmado or not destino.confirmado:
        raise conflito("ambos os plantoes devem estar em estado confirmado")

    turno_origem = obter_turno(sessao, origem.turno_id)
    turno_destino = obter_turno(sessao, destino.turno_id)

    profissional_a = obter_profissional(sessao, origem.profissional_id)
    profissional_b = obter_profissional(sessao, destino.profissional_id)
    if profissional_a.id == profissional_b.id:
        raise conflito("os plantoes devem pertencer a profissionais diferentes")

    # Conjuntos propostos: cada profissional abre mao do proprio plantao e
    # assume o turno do outro.
    propostos_a = itens_confirmados(
        sessao,
        profissional_a.id,
        excluir={origem.id},
        incluir=[item_do_turno(turno_destino, destino.id)],
    )
    propostos_b = itens_confirmados(
        sessao,
        profissional_b.id,
        excluir={destino.id},
        incluir=[item_do_turno(turno_origem, origem.id)],
    )
    validar_conjunto(sessao, profissional_a, propostos_a)
    validar_conjunto(sessao, profissional_b, propostos_b)

    origem.profissional_id = profissional_b.id
    destino.profissional_id = profissional_a.id
    troca.estado = models.ESTADO_TROCA_APROVADA
    troca.data_decisao = agora_utc()
    sessao.flush()

    recalcular_horas_extras(sessao, profissional_a)
    recalcular_horas_extras(sessao, profissional_b)
    return troca


def rejeitar_troca(sessao: Session, troca: models.Troca) -> models.Troca:
    """RF26 - registra a rejeicao da troca."""

    garantir_pendente(troca)
    troca.estado = models.ESTADO_TROCA_REJEITADA
    troca.data_decisao = agora_utc()
    sessao.flush()
    return troca


def garantir_pendente(troca: models.Troca) -> None:
    """RF27 - uma troca ja decidida nao pode receber nova decisao."""

    if troca.estado != models.ESTADO_TROCA_SOLICITADA:
        raise conflito(f"troca ja decidida (estado atual: {troca.estado})")


# ---------------------------------------------------------------------------
# Substituicoes
# ---------------------------------------------------------------------------


def entrar_na_fila(
    sessao: Session,
    turno: models.Turno,
    profissional: models.Profissional,
) -> models.Substituicao:
    """RF30 a RF32 - inscreve o profissional na fila de substituicao."""

    if contar_confirmados(sessao, turno.id) >= turno.cobertura_minima:
        raise conflito("turno ja atende a cobertura minima")
    if turno.especialidade_id not in profissional.especialidade_ids:
        raise conflito("profissional nao possui a especialidade exigida pelo turno")

    ja_na_fila = sessao.execute(
        select(models.Substituicao.id).where(
            models.Substituicao.turno_id == turno.id,
            models.Substituicao.profissional_id == profissional.id,
            models.Substituicao.estado.in_(
                (models.ESTADO_SUB_AGUARDANDO, models.ESTADO_SUB_CONVOCADO)
            ),
        )
    ).first()
    if ja_na_fila is not None:
        raise conflito("profissional ja esta na fila de substituicao deste turno")

    ultima = sessao.execute(
        select(func.max(models.Substituicao.posicao)).where(
            models.Substituicao.turno_id == turno.id,
            models.Substituicao.estado == models.ESTADO_SUB_AGUARDANDO,
        )
    ).scalar()

    substituicao = models.Substituicao(
        turno_id=turno.id,
        profissional_id=profissional.id,
        posicao=int(ultima or 0) + 1,
        estado=models.ESTADO_SUB_AGUARDANDO,
    )
    sessao.add(substituicao)
    sessao.flush()
    return substituicao


def sair_da_fila(sessao: Session, substituicao: models.Substituicao) -> models.Substituicao:
    """RF33 - cancela a inscricao e reorganiza as posicoes seguintes."""

    if substituicao.estado != models.ESTADO_SUB_AGUARDANDO:
        raise conflito(
            f"apenas substituicoes aguardando podem ser canceladas "
            f"(estado atual: {substituicao.estado})"
        )

    turno_id = substituicao.turno_id
    substituicao.estado = models.ESTADO_SUB_CANCELADA
    sessao.flush()

    # A cancelada sai da espera e abre uma lacuna; reatribuir 1..n as demais,
    # na ordem em que ja estavam, reduz em uma unidade exatamente as posicoes
    # posteriores (RF33, INV6).
    renumerar_fila(sessao, turno_id)
    return substituicao


def aceitar_convocacao(
    sessao: Session,
    substituicao: models.Substituicao,
) -> models.Plantao:
    """RF34 - converte a convocacao em plantao confirmado.

    Qualquer falha nas validacoes de RF14 a RF21 propaga 409 antes de
    qualquer ``commit``, mantendo a substituicao em ``convocado``.
    """

    if substituicao.estado != models.ESTADO_SUB_CONVOCADO:
        raise conflito(
            f"substituicao nao esta convocada (estado atual: {substituicao.estado})"
        )

    turno = obter_turno(sessao, substituicao.turno_id)
    profissional = obter_profissional(sessao, substituicao.profissional_id)

    plantao = alocar_plantao(sessao, turno, profissional)
    substituicao.estado = models.ESTADO_SUB_ATENDIDA
    sessao.flush()
    return plantao


# ---------------------------------------------------------------------------
# Ausencias
# ---------------------------------------------------------------------------


def registrar_ausencia(
    sessao: Session,
    profissional: models.Profissional,
    data_inicio: datetime,
    data_fim: datetime,
    tipo: str,
) -> models.Ausencia:
    """RF35 - registra a ausencia, recusando se houver plantao confirmado."""

    consulta = (
        select(models.Turno)
        .join(models.Plantao, models.Plantao.turno_id == models.Turno.id)
        .where(
            models.Plantao.profissional_id == profissional.id,
            models.Plantao.estado == models.ESTADO_PLANTAO_CONFIRMADO,
        )
    )
    for turno in sessao.execute(consulta).scalars().all():
        if ha_sobreposicao((turno.data_inicio, turno.data_fim), (data_inicio, data_fim)):
            raise conflito(
                "existe plantao confirmado sobreposto ao periodo de ausencia; "
                "cancele o plantao antes de registrar a ausencia"
            )

    ausencia = models.Ausencia(
        profissional_id=profissional.id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tipo=tipo,
    )
    sessao.add(ausencia)
    sessao.flush()
    return ausencia


# ---------------------------------------------------------------------------
# Vinculos de especialidade
# ---------------------------------------------------------------------------


def vincular_especialidade(
    sessao: Session,
    profissional: models.Profissional,
    especialidade: models.Especialidade,
) -> None:
    """RF06 - vincula a especialidade ao profissional."""

    if especialidade.id in profissional.especialidade_ids:
        raise conflito("vinculo ja existente")
    profissional.especialidades.append(especialidade)
    sessao.flush()


def desvincular_especialidade(
    sessao: Session,
    profissional: models.Profissional,
    especialidade: models.Especialidade,
) -> None:
    """RF07 - remove o vinculo, preservando INV4."""

    if especialidade.id not in profissional.especialidade_ids:
        raise nao_encontrado("vinculo nao encontrado")

    em_uso = sessao.execute(
        select(models.Plantao.id)
        .join(models.Turno, models.Turno.id == models.Plantao.turno_id)
        .where(
            models.Plantao.profissional_id == profissional.id,
            models.Plantao.estado == models.ESTADO_PLANTAO_CONFIRMADO,
            models.Turno.especialidade_id == especialidade.id,
        )
    ).first()
    if em_uso is not None:
        raise conflito(
            "INV4: existe plantao confirmado que depende desta especialidade"
        )

    profissional.especialidades.remove(especialidade)
    sessao.flush()


# ---------------------------------------------------------------------------
# Exclusao de turno
# ---------------------------------------------------------------------------


def excluir_turno(sessao: Session, turno: models.Turno) -> None:
    """RF12 - exclui o turno se nao houver plantao confirmado associado."""

    if contar_confirmados(sessao, turno.id) > 0:
        raise conflito("turno possui plantoes confirmados")
    sessao.delete(turno)
    sessao.flush()
