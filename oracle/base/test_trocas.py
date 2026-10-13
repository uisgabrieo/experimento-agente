"""Exercita os cenários de troca descritos em RF25 a RF27.

A faixa de dias 50 a 99 é reservada para estes testes. A atomicidade da
permuta definida em RF25 recebe atenção especial aqui.

Os plantões e as trocas são lidos no banco (ver `oracle/observacao.py`). A
versão 1 os consultava por `GET /plantoes/{id}`, rota que a especificação não
define.
"""
from oracle.auxiliares import checar_invariantes
from oracle.observacao import linha


def montar_par(criar_especialidade, criar_profissional, criar_turno,
               alocar, dia_origem, dia_destino):
    esp = criar_especialidade()
    profissional_origem = criar_profissional(especialidade_id=esp["id"])
    profissional_destino = criar_profissional(especialidade_id=esp["id"])
    turno_origem = criar_turno(esp["id"], dia=dia_origem, hora=8, duracao=8)
    turno_destino = criar_turno(esp["id"], dia=dia_destino, hora=8, duracao=8)
    resposta_origem = alocar(turno_origem["id"], profissional_origem["id"])
    resposta_destino = alocar(turno_destino["id"], profissional_destino["id"])
    assert resposta_origem.status_code == 201, resposta_origem.text
    assert resposta_destino.status_code == 201, resposta_destino.text
    return (esp, profissional_origem, profissional_destino,
            resposta_origem.json(), resposta_destino.json())


def solicitar(cliente, plantao_origem, plantao_destino):
    """Solicite a troca (RF24) e devolva o recurso criado."""
    resposta = cliente.post("/trocas", json={
        "plantao_origem_id": plantao_origem["id"],
        "plantao_destino_id": plantao_destino["id"]})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def situacao(plantao_id):
    """Devolva as colunas obrigatórias do plantão, como estão no banco."""
    registro = linha("plantoes", plantao_id)
    return (registro["turno_id"], registro["profissional_id"], registro["estado"])


def test_rf25_troca_valida_permuta_os_dois(cliente, criar_especialidade,
                                           criar_profissional, criar_turno, alocar):
    """RF25 — Aprove uma troca válida, permute os profissionais e registre a decisão."""
    _, profissional_origem, profissional_destino, plantao_origem, plantao_destino = (
        montar_par(criar_especialidade, criar_profissional, criar_turno, alocar, 50, 52))
    troca = solicitar(cliente, plantao_origem, plantao_destino)
    resposta = cliente.post(f"/trocas/{troca['id']}/aprovacao")
    assert resposta.status_code == 200, resposta.text

    assert linha("plantoes", plantao_origem["id"])["profissional_id"] == profissional_destino["id"]
    assert linha("plantoes", plantao_destino["id"])["profissional_id"] == profissional_origem["id"]
    registro = linha("trocas", troca["id"])
    assert registro["estado"] == "aprovada"
    assert registro["data_decisao"] is not None
    checar_invariantes()


def test_rf25_troca_invalida_nao_altera_nada(cliente, criar_especialidade,
                                             criar_profissional, criar_turno, alocar):
    """RF25 — Preserve os dois plantões quando a permuta for inválida."""
    esp = criar_especialidade()
    profissional_origem = criar_profissional(especialidade_id=esp["id"])
    profissional_destino = criar_profissional(especialidade_id=esp["id"])

    turno_origem = criar_turno(esp["id"], dia=60, hora=8, duracao=8)  # Das 08h às 16h.
    turno_destino = criar_turno(esp["id"], dia=61, hora=8, duracao=8)  # Também das 08h às 16h.
    turno_conflitante = criar_turno(esp["id"], dia=61, hora=20, duracao=6)  # Das 20h às 02h.

    origem = alocar(turno_origem["id"], profissional_origem["id"])
    destino = alocar(turno_destino["id"], profissional_destino["id"])
    conflitante = alocar(turno_conflitante["id"], profissional_origem["id"])
    for resposta in (origem, destino, conflitante):
        assert resposta.status_code == 201, resposta.text
    plantao_origem, plantao_destino = origem.json(), destino.json()
    # Ao assumir o destino, o profissional da origem ficaria com 4 horas de
    # descanso antes do plantão conflitante, o que viola INV2.

    antes = {pid: situacao(pid) for pid in (plantao_origem["id"], plantao_destino["id"])}
    troca = solicitar(cliente, plantao_origem, plantao_destino)
    resposta = cliente.post(f"/trocas/{troca['id']}/aprovacao")
    assert resposta.status_code == 409, resposta.text
    assert "detail" in resposta.json()

    for pid, situacao_anterior in antes.items():
        assert situacao(pid) == situacao_anterior, f"plantao {pid} foi alterado"
    checar_invariantes()


def test_rf27_decidir_troca_ja_decidida(cliente, criar_especialidade,
                                        criar_profissional, criar_turno, alocar):
    """RF26 e RF27 — Rejeite a troca e impeça uma segunda decisão."""
    _, _, _, plantao_origem, plantao_destino = montar_par(
        criar_especialidade, criar_profissional, criar_turno, alocar, 70, 72)
    troca = solicitar(cliente, plantao_origem, plantao_destino)
    rejeicao = cliente.post(f"/trocas/{troca['id']}/rejeicao")
    assert rejeicao.status_code == 200, rejeicao.text
    registro = linha("trocas", troca["id"])
    assert registro["estado"] == "rejeitada"
    assert registro["data_decisao"] is not None

    antes = {pid: situacao(pid) for pid in (plantao_origem["id"], plantao_destino["id"])}
    assert cliente.post(f"/trocas/{troca['id']}/aprovacao").status_code == 409
    assert linha("trocas", troca["id"])["estado"] == "rejeitada"
    for pid, situacao_anterior in antes.items():
        assert situacao(pid) == situacao_anterior, f"plantao {pid} foi alterado"
    checar_invariantes()


# O cenário de RF28 está em `test_complementares.py`, onde é possível verificar
# o efeito previsto — a troca passa para `rejeitada` — em vez de observar apenas
# a recusa de uma aprovação posterior.
