"""Submete o sistema a sequências geradas por testes de propriedades.

O Hypothesis combina operações que talvez não aparecessem nos cenários escritos
à mão. Depois de cada passo, todas as invariantes são verificadas; quando surge
uma falha, a ferramenta reduz a sequência ao menor contraexemplo reproduzível.

O foco não está em respostas HTTP específicas, mas na preservação das
invariantes. Por isso não há asserções sobre códigos ou corpos de resposta: até
uma operação recusada deve deixar o banco em um estado válido.
"""
import random
import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from oracle.auxiliares import checar_invariantes, email_unico, momento

OPERACOES = ["alocar", "cancelar", "solicitar_troca", "aprovar_troca",
             "inscrever_substituicao", "cancelar_substituicao", "registrar_ausencia"]


def montar_cenario(cliente, dia_base):
    resposta = cliente.post(
        "/especialidades", json={"nome": f"esp_{uuid.uuid4().hex[:12]}"}
    )
    assert resposta.status_code == 201, resposta.text
    esp = resposta.json()
    profs = []
    for _ in range(4):
        profissional = cliente.post("/profissionais", json={
            "nome": "P", "email": email_unico(), "carga_semanal": 44}).json()
        cliente.post(f"/profissionais/{profissional['id']}/especialidades",
                     json={"especialidade_id": esp["id"]})
        profs.append(profissional)
    turnos = []
    for deslocamento_dia in range(6):
        turno = cliente.post("/turnos", json={
            "data_inicio": momento(dia_base + deslocamento_dia, 8),
            "data_fim": momento(dia_base + deslocamento_dia, 16),
            "especialidade_id": esp["id"], "cobertura_minima": 1}).json()
        turnos.append(turno)
    return esp, profs, turnos


# O corpus permanece congelado durante todo o experimento.
#
# A geração é derandomizada para que todas as repetições recebam as mesmas
# operações. Do contrário, uma diferença entre r1 e r10 poderia vir da
# amostragem do instrumento, não do agente. Com `derandomize=True`, o Hypothesis
# reproduz o corpus, e o orquestrador recria o banco antes de cada medição.
@settings(max_examples=40, deadline=None, derandomize=True,
          database=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture,
                                 HealthCheck.too_slow])
@given(sequencia=st.lists(st.sampled_from(OPERACOES), min_size=5, max_size=25),
       semente=st.integers(min_value=0, max_value=10**6))
def test_invariantes_sob_sequencia_arbitraria(cliente, sequencia, semente):
    """Verifique INV1 a INV8 sem associar a sequência a um requisito isolado."""
    aleatorio = random.Random(semente)
    dia_base = 100 + (semente % 400) * 10
    esp, profs, turnos = montar_cenario(cliente, dia_base)
    plantoes, trocas, substituicoes = [], [], []

    for operacao in sequencia:
        prof = aleatorio.choice(profs)
        turno = aleatorio.choice(turnos)

        if operacao == "alocar":
            resposta = cliente.post("/plantoes", json={
                "turno_id": turno["id"], "profissional_id": prof["id"]})
            if resposta.status_code == 201:
                plantoes.append(resposta.json())

        elif operacao == "cancelar" and plantoes:
            alvo = aleatorio.choice(plantoes)
            cliente.delete(f"/plantoes/{alvo['id']}")
            plantoes.remove(alvo)

        elif operacao == "solicitar_troca" and len(plantoes) >= 2:
            plantao_origem, plantao_destino = aleatorio.sample(plantoes, 2)
            resposta = cliente.post("/trocas", json={
                "plantao_origem_id": plantao_origem["id"],
                "plantao_destino_id": plantao_destino["id"]})
            if resposta.status_code == 201:
                trocas.append(resposta.json())

        elif operacao == "aprovar_troca" and trocas:
            alvo = aleatorio.choice(trocas)
            cliente.post(f"/trocas/{alvo['id']}/aprovacao")
            trocas.remove(alvo)

        elif operacao == "inscrever_substituicao":
            resposta = cliente.post("/substituicoes", json={
                "turno_id": turno["id"], "profissional_id": prof["id"]})
            if resposta.status_code == 201:
                substituicoes.append(resposta.json())

        elif operacao == "cancelar_substituicao" and substituicoes:
            alvo = aleatorio.choice(substituicoes)
            cliente.delete(f"/substituicoes/{alvo['id']}")
            substituicoes.remove(alvo)

        elif operacao == "registrar_ausencia":
            dia = aleatorio.randint(dia_base, dia_base + 5)
            cliente.post("/ausencias", json={
                "profissional_id": prof["id"],
                "data_inicio": momento(dia, 0), "data_fim": momento(dia, 23),
                "tipo": "folga"})

        # Cada operação precisa preservar as invariantes, não apenas a sequência final.
        checar_invariantes()
