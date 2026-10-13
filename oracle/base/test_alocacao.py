"""Exercita os requisitos de alocação e cancelamento RF13 a RF22.

Esse conjunto concentra as regras de jornada, descanso, especialidade e
disponibilidade responsáveis por preservar as invariantes da escala.

A faixa de dias 0 a 49 é reservada para estes testes. O estado dos plantões e
as horas extras são lidos no banco (ver `oracle/observacao.py`).
"""
from oracle.auxiliares import checar_invariantes, momento
from oracle.observacao import horas_extras, linha, plantoes_confirmados


def test_rf13_alocar_plantao(cliente, criar_especialidade, criar_profissional,
                             criar_turno, alocar):
    """RF13 — Crie um plantão confirmado e retorne 201."""
    esp = criar_especialidade()
    prof = criar_profissional(especialidade_id=esp["id"])
    turno = criar_turno(esp["id"], dia=0)
    resposta = alocar(turno["id"], prof["id"])
    assert resposta.status_code == 201, resposta.text
    assert len(plantoes_confirmados(turno["id"], prof["id"])) == 1, (
        "o plantao deveria constar no banco em estado confirmado")
    checar_invariantes()


def test_rf14_sem_especialidade(cliente, criar_especialidade, criar_profissional,
                                criar_turno, alocar):
    """RF14 — Recuse quem não possui a especialidade exigida pelo turno."""
    esp = criar_especialidade()
    prof = criar_profissional()
    turno = criar_turno(esp["id"], dia=1)
    assert alocar(turno["id"], prof["id"]).status_code == 409
    checar_invariantes()


def test_rf15_sobreposicao(cliente, criar_especialidade, criar_profissional,
                           criar_turno, alocar):
    """RF15 — Recuse plantões sobrepostos para o mesmo profissional."""
    esp = criar_especialidade()
    prof = criar_profissional(especialidade_id=esp["id"])
    t1 = criar_turno(esp["id"], dia=2, hora=8, duracao=8)
    t2 = criar_turno(esp["id"], dia=2, hora=14, duracao=6)
    assert alocar(t1["id"], prof["id"]).status_code == 201
    assert alocar(t2["id"], prof["id"]).status_code == 409
    checar_invariantes()


def test_rf16_descanso_menor_que_11h(cliente, criar_especialidade,
                                     criar_profissional, criar_turno, alocar):
    """RF16 — Recuse um intervalo de descanso inferior a 11 horas."""
    esp = criar_especialidade()
    prof = criar_profissional(especialidade_id=esp["id"])
    t1 = criar_turno(esp["id"], dia=3, hora=8, duracao=8)
    t2 = criar_turno(esp["id"], dia=3, hora=22, duracao=6)
    assert alocar(t1["id"], prof["id"]).status_code == 201
    assert alocar(t2["id"], prof["id"]).status_code == 409
    checar_invariantes()


def test_rf16_descanso_de_exatamente_11h_permitido(cliente, criar_especialidade,
                                                   criar_profissional,
                                                   criar_turno, alocar):
    """RF16 — Aceite a fronteira de exatamente 11 horas de descanso."""
    esp = criar_especialidade()
    prof = criar_profissional(especialidade_id=esp["id"])
    t1 = criar_turno(esp["id"], dia=4, hora=8, duracao=8)
    t2 = criar_turno(esp["id"], dia=5, hora=3, duracao=5)
    assert alocar(t1["id"], prof["id"]).status_code == 201
    assert alocar(t2["id"], prof["id"]).status_code == 201
    checar_invariantes()


def test_rf17_excede_44_horas_semanais(cliente, criar_especialidade,
                                       criar_profissional, criar_turno, alocar):
    """RF17 — Recuse a alocação que ultrapassa 44 horas na semana."""
    esp = criar_especialidade()
    prof = criar_profissional(especialidade_id=esp["id"])
    aceitos = 0
    for dia in range(0, 4):
        resposta = alocar(criar_turno(esp["id"], dia=dia, hora=6, duracao=12)["id"], prof["id"])
        if resposta.status_code == 201:
            aceitos += 1
    assert aceitos == 3, "deveria aceitar 36h e recusar as 48h"
    checar_invariantes()


def test_rf18_sobreposicao_com_ausencia(cliente, criar_especialidade,
                                        criar_profissional, criar_turno, alocar):
    """RF18 — Recuse o plantão que coincide com uma ausência do profissional."""
    esp = criar_especialidade()
    prof = criar_profissional(especialidade_id=esp["id"])
    ausencia = cliente.post("/ausencias", json={
        "profissional_id": prof["id"], "data_inicio": momento(10, 0),
        "data_fim": momento(12, 0), "tipo": "ferias"})
    assert ausencia.status_code == 201, (
        f"precondicao: a ausencia deveria ser registrada (RF35): {ausencia.text}")
    turno = criar_turno(esp["id"], dia=11, hora=8)
    assert alocar(turno["id"], prof["id"]).status_code == 409
    checar_invariantes()


def test_rf19_setimo_dia_consecutivo(cliente, criar_especialidade,
                                     criar_profissional, criar_turno, alocar):
    """RF19 — Permita seis dias consecutivos de trabalho, mas não o sétimo."""
    esp = criar_especialidade()
    prof = criar_profissional(especialidade_id=esp["id"])
    aceitos = 0
    for dia in range(20, 27):
        resposta = alocar(criar_turno(esp["id"], dia=dia, hora=8, duracao=4)["id"], prof["id"])
        if resposta.status_code == 201:
            aceitos += 1
    assert aceitos == 6, "deveria aceitar 6 dias e recusar o setimo"
    checar_invariantes()


def test_rf20_profissional_inativo(cliente, criar_especialidade,
                                   criar_profissional, criar_turno, alocar):
    """RF20 — Recuse a alocação de um profissional inativo."""
    esp = criar_especialidade()
    prof = criar_profissional(ativo=False, especialidade_id=esp["id"])
    turno = criar_turno(esp["id"], dia=30)
    assert alocar(turno["id"], prof["id"]).status_code == 409
    checar_invariantes()


def test_rf21_ja_alocado_no_mesmo_turno(cliente, criar_especialidade,
                                        criar_profissional, criar_turno, alocar):
    """RF21 — Impeça que o mesmo profissional seja duplicado no turno."""
    esp = criar_especialidade()
    prof = criar_profissional(especialidade_id=esp["id"])
    turno = criar_turno(esp["id"], dia=31, cobertura=2)
    assert alocar(turno["id"], prof["id"]).status_code == 201
    assert alocar(turno["id"], prof["id"]).status_code == 409
    checar_invariantes()


def test_rf22_cancelamento_libera_horas(cliente, criar_especialidade,
                                        criar_profissional, criar_turno, alocar):
    """RF22 — Cancele o plantão e retire suas horas do cálculo de horas extras.

    Com carga semanal de 20 horas, dois plantões de 12 horas na mesma semana
    (sábado e domingo) somam 24 horas e geram 4 horas extras. Cancelado um
    deles, restam 12 horas e as horas extras voltam a zero.

    A versão 1 usava um único plantão de 12 horas, que nunca gera horas
    extras: o teste passava sem que o cancelamento liberasse coisa alguma.
    """
    esp = criar_especialidade()
    prof = criar_profissional(carga=20, especialidade_id=esp["id"])
    primeiro = criar_turno(esp["id"], dia=40, hora=8, duracao=12)
    segundo = criar_turno(esp["id"], dia=41, hora=8, duracao=12)
    resposta = alocar(primeiro["id"], prof["id"])
    assert resposta.status_code == 201, resposta.text
    plantao = resposta.json()
    assert alocar(segundo["id"], prof["id"]).status_code == 201
    assert abs(horas_extras(prof["id"]) - 4.0) < 0.01, (
        "precondicao: 24 horas na semana com carga de 20 deveriam gerar 4 horas "
        f"extras; registrado: {horas_extras(prof['id'])}")

    cancelamento = cliente.delete(f"/plantoes/{plantao['id']}")
    assert cancelamento.status_code == 200, cancelamento.text
    assert linha("plantoes", plantao["id"])["estado"] == "cancelado"
    assert abs(horas_extras(prof["id"])) < 0.01, (
        f"apos o cancelamento, horas extras deveriam ser 0; "
        f"registrado: {horas_extras(prof['id'])}")
    checar_invariantes()
