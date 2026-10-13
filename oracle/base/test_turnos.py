"""Exercita a criação e as consultas de turnos previstas em RF09 a RF11.

A faixa de dias 200 a 249 é reservada para estes testes.
"""

from oracle.auxiliares import checar_invariantes, momento, numero
from oracle.observacao import linha


def dados_turno(especialidade_id, dia, hora=8, duracao=8, cobertura=1):
    return {"data_inicio": momento(dia, hora),
            "data_fim": momento(dia, hora + duracao),
            "especialidade_id": especialidade_id,
            "cobertura_minima": cobertura}


# RF09 cobre a criação do turno e os limites de duração.

def test_rf09_criar_turno(cliente, criar_especialidade):
    """RF09 — Cadastre um turno de oito horas e retorne 201."""
    especialidade = criar_especialidade()
    resposta = cliente.post("/turnos", json=dados_turno(especialidade["id"], 200))
    assert resposta.status_code == 201, resposta.text
    registro = linha("turnos", resposta.json()["id"])
    assert registro is not None, "o turno criado nao consta no banco"
    assert registro["especialidade_id"] == especialidade["id"]
    assert int(registro["cobertura_minima"]) == 1
    checar_invariantes()


def test_rf09_duracao_curta_recusada(cliente, criar_especialidade):
    """RF09 — Recuse um turno de duas horas, abaixo do mínimo."""
    especialidade = criar_especialidade()
    resposta = cliente.post("/turnos",
                            json=dados_turno(especialidade["id"], 201, duracao=2))
    assert resposta.status_code == 422
    checar_invariantes()


def test_rf09_duracao_longa_recusada(cliente, criar_especialidade):
    """RF09 — Recuse um turno de 14 horas, acima do máximo."""
    especialidade = criar_especialidade()
    resposta = cliente.post("/turnos",
                            json=dados_turno(especialidade["id"], 202, duracao=14))
    assert resposta.status_code == 422
    checar_invariantes()


# RF10 e RF11 verificam a listagem e a consulta individual.

def test_rf10_listar_turnos(cliente, criar_especialidade, criar_turno):
    """RF10 — Inclua `itens` e `total` na resposta de `GET /turnos`."""
    especialidade = criar_especialidade()
    criar_turno(especialidade["id"], dia=203)
    resposta = cliente.get("/turnos")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert isinstance(corpo["itens"], list)
    assert numero(corpo["total"]) >= 1
    checar_invariantes()


def test_rf11_consultar_turno_inexistente(cliente):
    """RF11 — Retorne 404 ao consultar um turno inexistente."""
    resposta = cliente.get("/turnos/99999999")
    assert resposta.status_code == 404
    assert "detail" in resposta.json()


# As durações de fronteira completam o RF09.

def test_rf09_duracoes_de_4h_e_12h_aceitas(cliente, criar_especialidade):
    """RF09 — Aceite as durações de fronteira, de 4 e de 12 horas.

    O RF09 recusa apenas durações inferiores a 4 horas ou superiores a 12.

    Este teste substitui `test_rf09_campos_exatos_do_turno`, da versão 1, que
    exigia um conjunto exato de campos na resposta. A especificação não define
    esse corpo, e a seção 2.1 admite colunas adicionais.
    """
    especialidade = criar_especialidade()
    for dia, duracao in ((210, 4), (212, 12)):
        resposta = cliente.post(
            "/turnos", json=dados_turno(especialidade["id"], dia, duracao=duracao))
        assert resposta.status_code == 201, f"duracao de {duracao}h: {resposta.text}"
    checar_invariantes()
