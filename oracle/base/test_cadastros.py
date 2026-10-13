"""Exercita os requisitos de cadastro RF01 a RF06 e RF08.

Os cenários abrangem profissionais, especialidades e seus vínculos. Como
nenhum deles cria turnos, este módulo não precisa reservar uma faixa de datas.

Os efeitos persistidos são lidos no banco (ver `oracle/observacao.py`). Do
corpo das respostas usa-se apenas o `id` do recurso criado e o que o RF04
define.
"""

import uuid

from oracle.auxiliares import checar_invariantes, email_unico, numero
from oracle.observacao import linha, verdadeiro, vinculo_existe


def dados_profissional(**sobrescritas):
    """Monte um profissional válido e aplique os campos escolhidos pelo cenário."""
    base = {"nome": "Ana Silva", "email": email_unico(),
            "carga_semanal": 40, "ativo": True}
    base.update(sobrescritas)
    return base


# RF01 começa pelo caminho esperado de criação.

def test_rf01_criar_profissional(cliente):
    """RF01 — Cadastre o profissional e retorne 201.

    O registro deve conter os dados enviados e `horas_extras` iniciado em 0,
    como fixa a seção 3.
    """
    dados = dados_profissional()
    resposta = cliente.post("/profissionais", json=dados)
    assert resposta.status_code == 201, resposta.text
    registro = linha("profissionais", resposta.json()["id"])
    assert registro is not None, "o profissional criado nao consta no banco"
    assert registro["nome"] == dados["nome"]
    assert registro["email"] == dados["email"]
    assert int(registro["carga_semanal"]) == dados["carga_semanal"]
    assert verdadeiro(registro["ativo"])
    assert numero(registro["horas_extras"] or 0) == 0
    checar_invariantes()


# RF02 reúne as fronteiras de validação do profissional.

def test_rf02_email_sem_arroba(cliente):
    """RF02 — Recuse um endereço de e-mail que não contenha `@`."""
    resposta = cliente.post("/profissionais",
                            json=dados_profissional(email="usuarioexemplo.com"))
    assert resposta.status_code == 422
    checar_invariantes()


def test_rf02_email_curto_demais(cliente):
    """RF02 — Recuse um endereço de e-mail com menos de 13 caracteres."""
    resposta = cliente.post("/profissionais", json=dados_profissional(email="a@b.co"))
    assert resposta.status_code == 422
    checar_invariantes()


def test_rf02_nome_vazio(cliente):
    """RF02 — Recuse o cadastro quando o nome estiver vazio."""
    assert cliente.post("/profissionais",
                        json=dados_profissional(nome="")).status_code == 422
    checar_invariantes()


def test_rf02_carga_semanal_acima_do_maximo(cliente):
    """RF02 — Recuse uma carga semanal maior que 44 horas."""
    assert cliente.post("/profissionais",
                        json=dados_profissional(carga_semanal=50)).status_code == 422
    checar_invariantes()


def test_rf02_carga_semanal_abaixo_do_minimo(cliente):
    """RF02 — Recuse uma carga semanal menor que 20 horas."""
    assert cliente.post("/profissionais",
                        json=dados_profissional(carga_semanal=10)).status_code == 422
    checar_invariantes()


# RF03 verifica a unicidade do endereço de e-mail.

def test_rf03_email_duplicado(cliente):
    """RF03 — Retorne 409 ao repetir um endereço de e-mail já cadastrado."""
    email = email_unico()
    assert cliente.post("/profissionais",
                        json=dados_profissional(email=email)).status_code == 201
    assert cliente.post("/profissionais",
                        json=dados_profissional(email=email)).status_code == 409
    checar_invariantes()


# RF04 e RF05 cobrem as consultas de profissionais.

def test_rf04_listar_profissionais(cliente, criar_profissional):
    """RF04 — Inclua `itens` e `total` na resposta de `GET /profissionais`."""
    criar_profissional()
    resposta = cliente.get("/profissionais")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert isinstance(corpo["itens"], list)
    assert numero(corpo["total"]) >= 1
    checar_invariantes()


def test_rf04_limite_maximo_de_100(cliente, criar_profissional):
    """RF04 — Não devolva mais de 100 itens, ainda que o limite pedido seja maior.

    O RF04 fixa em 100 o máximo de `limite`, mas não determina se um valor
    acima disso é recusado ou reduzido ao máximo. As duas leituras são
    aceitas: recusa com resposta 4xx ou listagem com no máximo 100 itens. Para
    que a segunda seja de fato verificada, o cenário garante que existam mais
    de 100 profissionais cadastrados.

    A versão 1 exigia 422, o que a especificação não determina.
    """
    resposta = cliente.get("/profissionais", params={"limite": 500})
    if 400 <= resposta.status_code < 500:
        assert "detail" in resposta.json()
        return
    assert resposta.status_code == 200, resposta.text
    existentes = int(numero(resposta.json()["total"]))
    for _ in range(max(0, 101 - existentes)):
        criar_profissional()
    resposta = cliente.get("/profissionais", params={"limite": 500})
    assert resposta.status_code == 200, resposta.text
    assert len(resposta.json()["itens"]) <= 100


def test_rf05_consultar_profissional_inexistente(cliente):
    """RF05 — Retorne 404 ao consultar um profissional inexistente."""
    resposta = cliente.get("/profissionais/99999999")
    assert resposta.status_code == 404
    assert "detail" in resposta.json()


# RF06 e RF08 tratam das especialidades e de seus vínculos.

def test_rf06_vinculo_duplicado(cliente, criar_especialidade, criar_profissional):
    """RF06 — Crie o vínculo e retorne 409 ao repeti-lo."""
    especialidade = criar_especialidade()
    profissional = criar_profissional()
    caminho = f"/profissionais/{profissional['id']}/especialidades"
    corpo = {"especialidade_id": especialidade["id"]}
    assert cliente.post(caminho, json=corpo).status_code == 201
    assert vinculo_existe(profissional["id"], especialidade["id"])
    assert cliente.post(caminho, json=corpo).status_code == 409
    checar_invariantes()


def test_rf08_especialidade_duplicada(cliente):
    """RF08 — Retorne 409 ao repetir o nome de uma especialidade."""
    nome = f"esp_{uuid.uuid4().hex[:8]}"
    assert cliente.post("/especialidades", json={"nome": nome}).status_code == 201
    assert cliente.post("/especialidades", json={"nome": nome}).status_code == 409
    checar_invariantes()
