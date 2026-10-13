"""Exercita o campo `noturno` acrescentado pela Evolução 1.

Esta suíte se limita ao comportamento introduzido por E1. Os cenários vieram
de `artefatos/evolucao-e1.md`. A faixa de dias 300 a 349 é reservada a eles.

A E1 não fixa o nome de uma coluna nem o corpo da resposta de criação do
turno. Por isso, o registro de `noturno` é observado pelo filtro
`GET /turnos?noturno=`, que a própria E1 define, e os itens da listagem são
identificados pelo `id`. As horas extras são lidas no banco (ver
`oracle/observacao.py`).

Para aceitar E1, todos estes testes devem passar, nenhum teste das suítes
anteriores pode falhar e as invariantes precisam continuar válidas.
"""

from oracle.auxiliares import checar_invariantes, momento, numero
from oracle.observacao import horas_extras


def dados_turno(especialidade_id, dia, hora=8, duracao=8, cobertura=1, **extras):
    corpo = {"data_inicio": momento(dia, hora),
             "data_fim": momento(dia, hora + duracao),
             "especialidade_id": especialidade_id,
             "cobertura_minima": cobertura}
    corpo.update(extras)
    return corpo


def criar(cliente, especialidade_id, dia, **extras):
    """Cadastre o turno, confira o 201 e devolva o recurso criado."""
    resposta = cliente.post("/turnos", json=dados_turno(especialidade_id, dia, **extras))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def ids_filtrados(cliente, **parametros):
    """Devolva os ids devolvidos por `GET /turnos` com os filtros informados."""
    resposta = cliente.get("/turnos", params=parametros)
    assert resposta.status_code == 200, resposta.text
    return {item["id"] for item in resposta.json()["itens"]}


# Os primeiros cenários cobrem a criação e o valor padrão.

def test_e1_criar_turno_noturno(cliente, criar_especialidade):
    """E1 — Aceite `noturno=true` no cadastro e registre o turno como noturno."""
    especialidade = criar_especialidade()
    turno = criar(cliente, especialidade["id"], 300, noturno=True)
    assert turno["id"] in ids_filtrados(
        cliente, noturno="true", especialidade_id=especialidade["id"])
    assert turno["id"] not in ids_filtrados(
        cliente, noturno="false", especialidade_id=especialidade["id"])
    checar_invariantes()


def test_e1_valor_padrao_e_false(cliente, criar_especialidade):
    """E1 — Use `false` quando o campo `noturno` não for informado."""
    especialidade = criar_especialidade()
    turno = criar(cliente, especialidade["id"], 301)
    assert turno["id"] in ids_filtrados(
        cliente, noturno="false", especialidade_id=especialidade["id"])
    assert turno["id"] not in ids_filtrados(
        cliente, noturno="true", especialidade_id=especialidade["id"])
    checar_invariantes()


def test_e1_valor_invalido_recusado(cliente, criar_especialidade):
    """E1 — Recuse um valor não booleano em `noturno`.

    A E1 define o campo como booleano, mas não o código da recusa. Aceita-se
    422, usado pela especificação nas validações de dados (RF02, RF09) e
    adotado pelo FastAPI, ou 400. Em ambos os casos, o RF37 exige `detail`.
    """
    especialidade = criar_especialidade()
    resposta = cliente.post(
        "/turnos", json=dados_turno(especialidade["id"], 302, noturno="talvez"))
    assert resposta.status_code in (400, 422), resposta.text
    assert "detail" in resposta.json()
    checar_invariantes()


# Em seguida, a listagem é exercitada com o novo filtro.

def test_e1_filtro_noturno_verdadeiro(cliente, criar_especialidade):
    """E1 — Retorne somente turnos noturnos com o filtro `noturno=true`."""
    especialidade = criar_especialidade()
    noturno = criar(cliente, especialidade["id"], 305, noturno=True)
    criar(cliente, especialidade["id"], 306, noturno=False)
    assert ids_filtrados(cliente, noturno="true",
                         especialidade_id=especialidade["id"]) == {noturno["id"]}
    checar_invariantes()


def test_e1_filtro_noturno_falso(cliente, criar_especialidade):
    """E1 — Retorne somente turnos diurnos com o filtro `noturno=false`."""
    especialidade = criar_especialidade()
    criar(cliente, especialidade["id"], 307, noturno=True)
    diurno = criar(cliente, especialidade["id"], 308, noturno=False)
    assert ids_filtrados(cliente, noturno="false",
                         especialidade_id=especialidade["id"]) == {diurno["id"]}
    checar_invariantes()


def test_e1_filtro_combinado_com_especialidade(cliente, criar_especialidade):
    """E1 — Combine o filtro `noturno` com os filtros que já existiam."""
    primeira = criar_especialidade()
    segunda = criar_especialidade()
    alvo = criar(cliente, primeira["id"], 310, noturno=True)
    criar(cliente, segunda["id"], 311, noturno=True)
    criar(cliente, primeira["id"], 312, noturno=False)
    assert ids_filtrados(cliente, noturno="true",
                         especialidade_id=primeira["id"]) == {alvo["id"]}
    checar_invariantes()


# Os cenários finais isolam o efeito do adicional noturno de 20%.

def test_e1_adicional_incide_no_total_do_periodo(cliente, criar_especialidade,
                                                criar_profissional):
    """E1 — Aplique o adicional noturno ao total de horas do período.

    Três plantões noturnos de dez horas na mesma semana representam 30 horas
    reais e 36 horas após o adicional de 20%.

    O acréscimo incide em `horas_periodo`, mas não em `horas_extras`, cujo
    cálculo obedece a INV8 e considera a duração efetiva dos plantões.
    """
    especialidade = criar_especialidade()
    profissional = criar_profissional(carga=44, especialidade_id=especialidade["id"])

    for dia in (315, 317, 319):
        turno = criar(cliente, especialidade["id"], dia, hora=8, duracao=10, noturno=True)
        assert cliente.post("/plantoes", json={
            "turno_id": turno["id"],
            "profissional_id": profissional["id"]}).status_code == 201

    escala = cliente.get(f"/profissionais/{profissional['id']}/escala",
                         params={"de": momento(314, 0), "ate": momento(321, 0)})
    assert escala.status_code == 200, escala.text
    obtido = numero(escala.json()["horas_periodo"])
    assert abs(obtido - 36.0) < 0.01, (
        f"esperado 36.0 (30h reais x 1.2), obtido {obtido}")
    checar_invariantes()


def test_e1_adicional_nao_altera_horas_extras(cliente, criar_especialidade,
                                              criar_profissional):
    """E1 — Não aplique o adicional noturno ao cálculo de horas extras.

    Para uma carga semanal de 20 horas e três plantões noturnos de dez horas, o
    excedente real é de dez horas. Aplicar o adicional elevaria o valor para 16
    horas e violaria INV8.
    """
    especialidade = criar_especialidade()
    profissional = criar_profissional(carga=20, especialidade_id=especialidade["id"])

    for dia in (329, 331, 333):
        turno = criar(cliente, especialidade["id"], dia, hora=8, duracao=10, noturno=True)
        assert cliente.post("/plantoes", json={
            "turno_id": turno["id"],
            "profissional_id": profissional["id"]}).status_code == 201

    obtido = horas_extras(profissional["id"])
    assert abs(obtido - 10.0) < 0.01, (
        f"esperado 10.0 (30h reais menos carga de 20h, sem adicional), obtido {obtido}")
    checar_invariantes()


def test_e1_adicional_nao_altera_limite_semanal(cliente, criar_especialidade,
                                                criar_profissional):
    """E1 — Não use o adicional noturno para aplicar o teto semanal de 44 horas.

    Quatro plantões noturnos de dez horas somam 40 horas reais e devem ser
    aceitos. Se o adicional entrasse nesse limite, o total chegaria a 48 horas
    e o quarto plantão seria recusado indevidamente.
    """
    especialidade = criar_especialidade()
    profissional = criar_profissional(carga=44, especialidade_id=especialidade["id"])

    aceitos = 0
    for dia in (336, 338, 340, 342):  # Os dias são alternados, mas pertencem à mesma semana.
        turno = criar(cliente, especialidade["id"], dia, hora=8, duracao=10, noturno=True)
        resposta = cliente.post("/plantoes", json={
            "turno_id": turno["id"], "profissional_id": profissional["id"]})
        if resposta.status_code == 201:
            aceitos += 1

    assert aceitos == 4, (
        "40 horas reais estao abaixo do teto de 44; o adicional de vinte por "
        "cento nao deve ser considerado no limite semanal")
    checar_invariantes()
