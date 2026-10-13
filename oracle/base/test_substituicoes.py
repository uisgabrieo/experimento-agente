"""Exercita substituições e ausências conforme RF30 a RF33, RF35 e RF36.

A faixa de dias 250 a 299 é reservada para estes testes.

RF31 só permite entrar na fila quando a cobertura mínima ainda não foi
atingida. Por isso, os cenários usam cobertura 2 com uma pessoa alocada ou
cobertura 1 sem ninguém alocado.

Posições e estados das inscrições são lidos no banco (ver
`oracle/observacao.py`). A rota do RF36 é verificada apenas pelo que o RF36
determina: conteúdo e ordem da fila, não o formato do corpo.
"""

from oracle.auxiliares import checar_invariantes, momento
from oracle.observacao import (estado_da_substituicao, ids_aguardando_em_ordem,
                               itens_da_fila, linha, posicoes_aguardando)


def inscrever(cliente, turno, profissional):
    """Inscreva o profissional na fila (RF30) e devolva o id da inscrição."""
    resposta = cliente.post("/substituicoes", json={
        "turno_id": turno["id"], "profissional_id": profissional["id"]})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


# RF30 acompanha a entrada na fila de substituição.

def test_rf30_entrar_na_fila(cliente, criar_especialidade,
                             criar_profissional, criar_turno):
    """RF30 — Crie a inscrição em `aguardando`, na posição 1."""
    especialidade = criar_especialidade()
    profissional = criar_profissional(especialidade_id=especialidade["id"])
    turno = criar_turno(especialidade["id"], dia=250)
    registro = linha("substituicoes", inscrever(cliente, turno, profissional))
    assert registro is not None, "a inscricao nao consta no banco"
    assert int(registro["posicao"]) == 1
    assert registro["estado"] == "aguardando"
    checar_invariantes()


def test_rf30_segunda_inscricao_recebe_posicao_2(cliente, criar_especialidade,
                                                 criar_profissional, criar_turno):
    """RF30 — Atribua posições sequenciais às novas inscrições."""
    especialidade = criar_especialidade()
    primeiro = criar_profissional(especialidade_id=especialidade["id"])
    segundo = criar_profissional(especialidade_id=especialidade["id"])
    turno = criar_turno(especialidade["id"], dia=251)
    inscrever(cliente, turno, primeiro)
    registro = linha("substituicoes", inscrever(cliente, turno, segundo))
    assert int(registro["posicao"]) == 2
    checar_invariantes()


# RF31 e RF32 definem quando uma inscrição deve ser recusada.

def test_rf31_cobertura_ja_atendida(cliente, criar_especialidade,
                                    criar_profissional, criar_turno, alocar):
    """RF31 — Recuse inscrições quando a cobertura mínima já estiver atendida."""
    especialidade = criar_especialidade()
    alocado = criar_profissional(especialidade_id=especialidade["id"])
    candidato = criar_profissional(especialidade_id=especialidade["id"])
    turno = criar_turno(especialidade["id"], dia=252, cobertura=1)
    assert alocar(turno["id"], alocado["id"]).status_code == 201
    resposta = cliente.post("/substituicoes", json={
        "turno_id": turno["id"], "profissional_id": candidato["id"]})
    assert resposta.status_code == 409
    checar_invariantes()


def test_rf32_sem_especialidade(cliente, criar_especialidade,
                                criar_profissional, criar_turno):
    """RF32 — Recuse quem não possui a especialidade exigida pelo turno."""
    especialidade = criar_especialidade()
    profissional = criar_profissional()  # Criado sem vínculo com a especialidade.
    turno = criar_turno(especialidade["id"], dia=253)
    resposta = cliente.post("/substituicoes", json={
        "turno_id": turno["id"], "profissional_id": profissional["id"]})
    assert resposta.status_code == 409
    checar_invariantes()


# RF33 cobre a saída voluntária da fila.

def test_rf33_cancelar_inscricao(cliente, criar_especialidade,
                                 criar_profissional, criar_turno):
    """RF33 — Cancele uma inscrição em espera, retorne 204 e marque-a como cancelada."""
    especialidade = criar_especialidade()
    profissional = criar_profissional(especialidade_id=especialidade["id"])
    turno = criar_turno(especialidade["id"], dia=254)
    identificador = inscrever(cliente, turno, profissional)
    assert cliente.delete(f"/substituicoes/{identificador}").status_code == 204
    assert estado_da_substituicao(identificador) == "cancelada"
    checar_invariantes()


def test_rf33_cancelamento_reordena_a_fila(cliente, criar_especialidade,
                                           criar_profissional, criar_turno):
    """RF33 — Reordene a fila quando a primeira inscrição for cancelada.

    A inscrição seguinte deve assumir a posição 1, mantendo a fila sem lacunas
    como determina INV6.
    """
    especialidade = criar_especialidade()
    primeiro = criar_profissional(especialidade_id=especialidade["id"])
    segundo = criar_profissional(especialidade_id=especialidade["id"])
    turno = criar_turno(especialidade["id"], dia=255)

    inscricao_um = inscrever(cliente, turno, primeiro)
    inscrever(cliente, turno, segundo)
    assert cliente.delete(f"/substituicoes/{inscricao_um}").status_code == 204

    assert posicoes_aguardando(turno["id"]) == [(segundo["id"], 1)]
    checar_invariantes()


# RF36 verifica a consulta da fila atual.

def test_rf36_consultar_fila(cliente, criar_especialidade,
                             criar_profissional, criar_turno):
    """RF36 — Devolva a fila em `aguardando`, ordenada por posição.

    Três inscrições entram na fila e a segunda é cancelada. A rota deve
    devolver exatamente as inscrições que o banco registra em `aguardando`, na
    ordem de `posicao`. O corpo pode ser a lista ou o envelope `{itens}`: o
    RF36 não fixa o formato. Os itens são identificados pelo `id`.
    """
    especialidade = criar_especialidade()
    turno = criar_turno(especialidade["id"], dia=256)
    inscricoes = [inscrever(cliente, turno,
                            criar_profissional(especialidade_id=especialidade["id"]))
                  for _ in range(3)]
    cliente.delete(f"/substituicoes/{inscricoes[1]}")

    resposta = cliente.get(f"/turnos/{turno['id']}/substituicoes")
    assert resposta.status_code == 200, resposta.text
    devolvidas = [item["id"] for item in itens_da_fila(resposta)]
    esperadas = ids_aguardando_em_ordem(turno["id"])
    assert len(esperadas) >= 2, f"precondicao: fila com inscricoes em espera; banco: {esperadas}"
    assert devolvidas == esperadas
    checar_invariantes()


# RF35 encerra o módulo com o registro de ausências.

def test_rf35_ausencia_com_plantao_sobreposto(cliente, criar_especialidade,
                                              criar_profissional, criar_turno,
                                              alocar):
    """RF35 — Retorne 409 para uma ausência que coincida com plantão confirmado."""
    especialidade = criar_especialidade()
    profissional = criar_profissional(especialidade_id=especialidade["id"])
    turno = criar_turno(especialidade["id"], dia=260, hora=8, duracao=8)
    assert alocar(turno["id"], profissional["id"]).status_code == 201

    resposta = cliente.post("/ausencias", json={
        "profissional_id": profissional["id"],
        "data_inicio": momento(260, 0), "data_fim": momento(261, 0),
        "tipo": "atestado"})
    assert resposta.status_code == 409
    checar_invariantes()
