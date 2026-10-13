"""Exercita os requisitos transversais RF37 e RF38.

Nenhum cenário cria turnos, portanto não há uma faixa de datas reservada.
"""


def test_rf37_erro_404_contem_detail(cliente):
    """RF37 — Inclua a chave `detail` em toda resposta da classe 4xx."""
    resposta = cliente.get("/profissionais/99999999")
    assert resposta.status_code == 404
    assert "detail" in resposta.json()


def test_rf38_rota_de_saude(cliente):
    """RF38 — Faça `GET /saude` devolver exatamente `{"status": "ok"}`."""
    resposta = cliente.get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
