"""Reúne os cenários complementares de RF07, RF12, RF23, RF24, RF28, RF29 e RF34.

A faixa de dias 400 a 449 é reservada para estes testes.

Os requisitos aparecem juntos porque seus cenários atravessam mais de uma
entidade e não se encaixam naturalmente nos outros módulos. Os efeitos
persistidos são lidos no banco (ver `oracle/observacao.py`).
"""

from oracle.auxiliares import checar_invariantes, momento, numero
from oracle.observacao import (estado_da_substituicao, linha,
                               plantoes_confirmados, vinculo_existe)


def alocar_confirmado(alocar, turno, profissional):
    """Aloque e confira o 201; devolva o plantão criado."""
    resposta = alocar(turno["id"], profissional["id"])
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def solicitar(cliente, plantao_origem, plantao_destino):
    """Solicite a troca (RF24) e devolva o recurso criado."""
    resposta = cliente.post("/trocas", json={
        "plantao_origem_id": plantao_origem["id"],
        "plantao_destino_id": plantao_destino["id"]})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def cancelar(cliente, plantao):
    """Cancele o plantão e confira o efeito no banco, não o código de resposta.

    O código do cancelamento é verificado no teste do próprio RF22. Aqui, só o
    efeito importa como pré-condição.
    """
    cliente.delete(f"/plantoes/{plantao['id']}")
    assert linha("plantoes", plantao["id"])["estado"] == "cancelado", (
        "precondicao: o plantao deveria estar cancelado (RF22)")


# RF07 trata da remoção de uma especialidade do profissional.

def test_rf07_remover_especialidade_sem_plantao(cliente, criar_especialidade,
                                                criar_profissional):
    """RF07 — Remova o vínculo sem plantão confirmado e retorne 204."""
    especialidade = criar_especialidade()
    profissional = criar_profissional(especialidade_id=especialidade["id"])
    resposta = cliente.delete(
        f"/profissionais/{profissional['id']}/especialidades/{especialidade['id']}")
    assert resposta.status_code == 204, resposta.text
    assert not vinculo_existe(profissional["id"], especialidade["id"])
    checar_invariantes()


def test_rf07_remover_especialidade_com_plantao_confirmado(
        cliente, criar_especialidade, criar_profissional, criar_turno, alocar):
    """RF07 — Recuse a remoção se houver plantão confirmado na especialidade.

    A recusa preserva INV4, pois o plantão confirmado precisa permanecer ligado
    a um profissional que possua a especialidade exigida pelo turno.
    """
    especialidade = criar_especialidade()
    profissional = criar_profissional(especialidade_id=especialidade["id"])
    turno = criar_turno(especialidade["id"], dia=400)
    alocar_confirmado(alocar, turno, profissional)

    resposta = cliente.delete(
        f"/profissionais/{profissional['id']}/especialidades/{especialidade['id']}")
    assert resposta.status_code == 409
    assert "detail" in resposta.json()
    assert vinculo_existe(profissional["id"], especialidade["id"])
    checar_invariantes()


# RF12 cobre a exclusão de turnos com e sem plantão confirmado.

def test_rf12_excluir_turno_sem_plantao(cliente, criar_especialidade, criar_turno):
    """RF12 — Permita excluir um turno sem plantão confirmado.

    Depois da exclusão, o turno deixa de existir e a consulta do RF11 retorna 404.
    """
    especialidade = criar_especialidade()
    turno = criar_turno(especialidade["id"], dia=402)
    assert cliente.delete(f"/turnos/{turno['id']}").status_code == 204
    assert cliente.get(f"/turnos/{turno['id']}").status_code == 404
    checar_invariantes()


def test_rf12_excluir_turno_com_plantao_confirmado(
        cliente, criar_especialidade, criar_profissional, criar_turno, alocar):
    """RF12 — Preserve um turno que ainda tenha plantão confirmado."""
    especialidade = criar_especialidade()
    profissional = criar_profissional(especialidade_id=especialidade["id"])
    turno = criar_turno(especialidade["id"], dia=404)
    alocar_confirmado(alocar, turno, profissional)

    resposta = cliente.delete(f"/turnos/{turno['id']}")
    assert resposta.status_code == 409
    assert linha("turnos", turno["id"]) is not None, "o turno nao poderia ter sido excluido"
    checar_invariantes()


# RF23 verifica a consulta da escala do profissional.

def test_rf23_consultar_escala(cliente, criar_especialidade,
                               criar_profissional, criar_turno, alocar):
    """RF23 — Devolva `itens`, `total` e `horas_periodo` na consulta da escala.

    Dois plantões de oito horas totalizam 16 horas. Esse valor serve como linha
    de base para E1, que acrescenta o adicional a `horas_periodo`.
    """
    especialidade = criar_especialidade()
    profissional = criar_profissional(especialidade_id=especialidade["id"])
    for dia in (406, 408):
        turno = criar_turno(especialidade["id"], dia=dia, hora=8, duracao=8)
        alocar_confirmado(alocar, turno, profissional)

    resposta = cliente.get(f"/profissionais/{profissional['id']}/escala",
                           params={"de": momento(405, 0), "ate": momento(410, 0)})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert isinstance(corpo["itens"], list)
    assert numero(corpo["total"]) == 2
    assert abs(numero(corpo["horas_periodo"]) - 16.0) < 0.01
    checar_invariantes()


def test_rf23_escala_respeita_o_periodo(cliente, criar_especialidade,
                                        criar_profissional, criar_turno, alocar):
    """RF23 — Ignore no total os plantões que estão fora do período consultado."""
    especialidade = criar_especialidade()
    profissional = criar_profissional(especialidade_id=especialidade["id"])
    turno_dentro = criar_turno(especialidade["id"], dia=412, hora=8, duracao=8)
    turno_fora = criar_turno(especialidade["id"], dia=420, hora=8, duracao=8)
    alocar_confirmado(alocar, turno_dentro, profissional)
    alocar_confirmado(alocar, turno_fora, profissional)

    resposta = cliente.get(f"/profissionais/{profissional['id']}/escala",
                           params={"de": momento(411, 0), "ate": momento(414, 0)})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert numero(corpo["total"]) == 1
    assert abs(numero(corpo["horas_periodo"]) - 8.0) < 0.01
    checar_invariantes()


# RF24 reúne os casos em que a solicitação de troca deve ser recusada.

def test_rf24_troca_entre_plantoes_do_mesmo_profissional(
        cliente, criar_especialidade, criar_profissional, criar_turno, alocar):
    """RF24 — Exija profissionais diferentes nos dois plantões da troca."""
    especialidade = criar_especialidade()
    profissional = criar_profissional(especialidade_id=especialidade["id"])
    primeiro = alocar_confirmado(alocar, criar_turno(especialidade["id"], dia=424), profissional)
    segundo = alocar_confirmado(alocar, criar_turno(especialidade["id"], dia=426), profissional)

    resposta = cliente.post("/trocas", json={
        "plantao_origem_id": primeiro["id"], "plantao_destino_id": segundo["id"]})
    assert resposta.status_code == 409
    checar_invariantes()


def test_rf24_troca_com_plantao_cancelado(
        cliente, criar_especialidade, criar_profissional, criar_turno, alocar):
    """RF24 — Exija que ambos os plantões estejam confirmados."""
    especialidade = criar_especialidade()
    primeiro_prof = criar_profissional(especialidade_id=especialidade["id"])
    segundo_prof = criar_profissional(especialidade_id=especialidade["id"])
    primeiro = alocar_confirmado(alocar, criar_turno(especialidade["id"], dia=428), primeiro_prof)
    segundo = alocar_confirmado(alocar, criar_turno(especialidade["id"], dia=430), segundo_prof)
    cancelar(cliente, primeiro)

    resposta = cliente.post("/trocas", json={
        "plantao_origem_id": primeiro["id"], "plantao_destino_id": segundo["id"]})
    assert resposta.status_code == 409
    checar_invariantes()


# RF29 cobre a listagem filtrada de trocas.

def test_rf29_listar_trocas_com_filtro(
        cliente, criar_especialidade, criar_profissional, criar_turno, alocar):
    """RF29 — Filtre `GET /trocas` por estado e devolva `itens` e `total`.

    Uma troca fica `solicitada` e outra é rejeitada. A consulta filtrada deve
    incluir a primeira e só pode devolver trocas cujo estado registrado seja
    `solicitada`. Os itens são identificados pelo `id`; o estado de cada um é
    conferido no banco, sem depender dos campos que o item expõe.
    """
    especialidade = criar_especialidade()
    plantoes = []
    for dia in (432, 434, 436, 438):
        profissional = criar_profissional(especialidade_id=especialidade["id"])
        turno = criar_turno(especialidade["id"], dia=dia)
        plantoes.append(alocar_confirmado(alocar, turno, profissional))
    pendente = solicitar(cliente, plantoes[0], plantoes[1])
    outra = solicitar(cliente, plantoes[2], plantoes[3])
    cliente.post(f"/trocas/{outra['id']}/rejeicao")

    resposta = cliente.get("/trocas", params={"estado": "solicitada"})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert isinstance(corpo["itens"], list)
    assert "total" in corpo
    devolvidas = [item["id"] for item in corpo["itens"]]
    assert pendente["id"] in devolvidas
    estados = {troca_id: (linha("trocas", troca_id) or {}).get("estado")
               for troca_id in devolvidas}
    assert all(estado == "solicitada" for estado in estados.values()), (
        f"o filtro devolveu trocas em outros estados: {estados}")
    checar_invariantes()


# RF28 e RF34 exercitam o cancelamento e o aceite na fila de substituição.

def test_rf28_cancelamento_rejeita_troca_automaticamente(
        cliente, criar_especialidade, criar_profissional, criar_turno, alocar):
    """RF28 — Rejeite a troca pendente quando um de seus plantões for cancelado.

    Logo após o cancelamento, o estado deve ser `rejeitada` e `data_decisao`
    já deve estar preenchida.
    """
    especialidade = criar_especialidade()
    primeiro_prof = criar_profissional(especialidade_id=especialidade["id"])
    segundo_prof = criar_profissional(especialidade_id=especialidade["id"])
    primeiro = alocar_confirmado(alocar, criar_turno(especialidade["id"], dia=444), primeiro_prof)
    segundo = alocar_confirmado(alocar, criar_turno(especialidade["id"], dia=446), segundo_prof)
    troca = solicitar(cliente, primeiro, segundo)
    assert linha("trocas", troca["id"])["estado"] == "solicitada"

    cancelar(cliente, primeiro)

    registro = linha("trocas", troca["id"])
    assert registro["estado"] == "rejeitada"
    assert registro["data_decisao"] is not None
    checar_invariantes()


def test_rf34_aceite_fora_do_estado_convocado(
        cliente, criar_especialidade, criar_profissional, criar_turno):
    """RF34 — Retorne 409 ao aceitar uma inscrição que não foi convocada."""
    especialidade = criar_especialidade()
    profissional = criar_profissional(especialidade_id=especialidade["id"])
    turno = criar_turno(especialidade["id"], dia=440)
    inscricao = cliente.post("/substituicoes", json={
        "turno_id": turno["id"], "profissional_id": profissional["id"]})
    assert inscricao.status_code == 201, inscricao.text
    identificador = inscricao.json()["id"]
    estado_inicial = estado_da_substituicao(identificador)
    assert estado_inicial != "convocado", "precondicao: a inscricao nao pode estar convocada"

    resposta = cliente.post(f"/substituicoes/{identificador}/aceite")
    assert resposta.status_code == 409, resposta.text
    assert estado_da_substituicao(identificador) == estado_inicial
    assert plantoes_confirmados(turno["id"]) == []
    checar_invariantes()


def test_rf34_aceite_cria_plantao(cliente, criar_especialidade,
                                  criar_profissional, criar_turno, alocar):
    """RF34 — Aceite a convocação: crie o plantão e marque a substituição como atendida.

    Sequência, toda prevista na especificação: com o turno abaixo da cobertura
    mínima, o substituto entra na fila (RF30, RF31); um profissional é alocado
    e a cobertura é atingida; o cancelamento desse plantão deixa o turno
    abaixo da cobertura e convoca a posição 1 (RF22); o aceite cria o plantão
    (RF34).

    Os estados `convocado` e `atendida` e o plantão criado são lidos no banco.
    A rota do RF36 devolve apenas inscrições em `aguardando`, e o RF34 não
    define o corpo da resposta do aceite. A versão 1 deste teste observava a
    convocação por essa rota e exigia um corpo de resposta: reprovava qualquer
    implementação aderente.
    """
    especialidade = criar_especialidade()
    alocado = criar_profissional(especialidade_id=especialidade["id"])
    substituto = criar_profissional(especialidade_id=especialidade["id"])
    turno = criar_turno(especialidade["id"], dia=448, cobertura=1)

    inscricao = cliente.post("/substituicoes", json={
        "turno_id": turno["id"], "profissional_id": substituto["id"]})
    assert inscricao.status_code == 201, inscricao.text
    inscricao = inscricao.json()

    plantao = alocar_confirmado(alocar, turno, alocado)
    cancelar(cliente, plantao)

    estado_antes = estado_da_substituicao(inscricao["id"])
    assert estado_antes == "convocado", (
        f"esperava convocacao apos o cancelamento (RF22); estado atual: {estado_antes}")

    resposta = cliente.post(f"/substituicoes/{inscricao['id']}/aceite")
    assert resposta.status_code == 201, resposta.text
    assert estado_da_substituicao(inscricao["id"]) == "atendida"
    criados = plantoes_confirmados(turno["id"], substituto["id"])
    assert len(criados) == 1, f"esperava um plantao confirmado; obtido: {criados}"
    checar_invariantes()
