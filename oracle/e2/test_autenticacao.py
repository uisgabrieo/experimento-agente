"""Exercita a autenticação por perfil e a auditoria acrescentadas em E2.

Os cenários derivam de `artefatos/evolucao-e2.md`. A faixa de dias 350 a 399
é reservada a eles.

Dois cuidados distinguem esta versão da versão 1.

1. Momento da leitura das chaves. A E2 diz que as chaves vêm das variáveis de
   ambiente, sem fixar quando são lidas. A fixture `autenticacao_ativa` define
   as variáveis e importa de novo a aplicação, de modo que uma implementação
   que leia as chaves a cada requisição e outra que as leia uma única vez, na
   importação ou na inicialização, sejam avaliadas da mesma forma. A versão 1
   só aceitava a leitura a cada requisição.

2. Observação da auditoria. A E2 fixa a tabela `auditoria` e suas colunas,
   mas não a ordem nem a paginação de `GET /auditoria`. Os registros são lidos
   no banco (ver `oracle/observacao.py`). A versão 1 dependia da ordem da
   listagem e exigia que leituras não fossem auditadas, o que a E2 não proíbe.

E2 só é aceita se todos estes testes passarem, os testes das suítes base e E1
continuarem aprovados e as invariantes permanecerem válidas.
"""

import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oracle.auxiliares import checar_invariantes, email_unico, momento, numero
from oracle.invariantes import _converter_data_hora
from oracle.observacao import colunas, contar, ultimo_registro

CHAVE_COORD = "key-coord-tcc-V1"
CHAVE_PROF = "key-prod-tcc-V1"


def _modulos_da_aplicacao():
    """Devolva os módulos carregados da pasta da aplicação avaliada.

    A pasta é a que contém `app/`. Inclui módulos fora de `app/` que a
    aplicação tenha importado dessa mesma pasta. O oráculo fica em outra árvore
    e nunca entra nesta seleção.
    """
    principal = sys.modules.get("app.main")
    arquivo = getattr(principal, "__file__", None)
    if not arquivo:
        return {nome: modulo for nome, modulo in sys.modules.items()
                if nome == "app" or nome.startswith("app.")}
    raiz = Path(arquivo).resolve().parent.parent
    selecionados = {}
    for nome, modulo in list(sys.modules.items()):
        origem = getattr(modulo, "__file__", None)
        if not origem:
            if nome == "app" or nome.startswith("app."):
                selecionados[nome] = modulo
            continue
        try:
            Path(origem).resolve().relative_to(raiz)
        except ValueError:
            continue
        selecionados[nome] = modulo
    return selecionados


@pytest.fixture
def autenticacao_ativa(criar_especialidade):
    """Ative a autenticação em uma instância da aplicação importada com as chaves.

    Os dados de apoio são preparados antes da ativação, pela instância usada
    no restante da sessão. Ao final, as variáveis são removidas e os módulos
    originais restaurados: a suíte base continua sem autenticação, qualquer
    que seja o momento em que a implementação lê as chaves.
    """
    especialidade = criar_especialidade()
    originais = _modulos_da_aplicacao()
    os.environ["CHAVE_COORDENADOR"] = CHAVE_COORD
    os.environ["CHAVE_PROFISSIONAL"] = CHAVE_PROF
    for nome in originais:
        sys.modules.pop(nome, None)
    try:
        modulo_principal = importlib.import_module("app.main")
        with TestClient(modulo_principal.app) as cliente_ativo:
            yield {"cliente": cliente_ativo,
                   "coordenador": {"X-Auth-Key": CHAVE_COORD},
                   "profissional": {"X-Auth-Key": CHAVE_PROF},
                   "especialidade_id": especialidade["id"]}
    finally:
        os.environ.pop("CHAVE_COORDENADOR", None)
        os.environ.pop("CHAVE_PROFISSIONAL", None)
        for nome in list(_modulos_da_aplicacao()):
            sys.modules.pop(nome, None)
        sys.modules.update(originais)


def dados_profissional():
    return {"nome": "Teste E2", "email": email_unico(),
            "carga_semanal": 40, "ativo": True}


# Primeiro, os cenários preservam o comportamento sem autenticação.

def test_e2_sem_variaveis_comportamento_anterior(cliente):
    """E2 — Preserve o comportamento anterior quando não houver chaves.

    Nessa configuração, as rotas dispensam cabeçalho. É também a configuração
    da suíte base, o que mantém válida a medição de regressões.
    """
    assert "CHAVE_COORDENADOR" not in os.environ
    assert "CHAVE_PROFISSIONAL" not in os.environ
    resposta = cliente.post("/profissionais", json=dados_profissional())
    assert resposta.status_code == 201, resposta.text
    checar_invariantes()


def test_e2_auditoria_acessivel_sem_chave_quando_desativada(cliente):
    """E2 — Dispense o cabeçalho em `GET /auditoria` sem autenticação ativa."""
    resposta = cliente.get("/auditoria")
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert isinstance(corpo["itens"], list)
    assert numero(corpo["total"]) >= 0


def test_e2_perfil_registrado_como_desativada(cliente):
    """E2 — Registre o perfil `desativada` quando não houver autenticação."""
    antes = contar("auditoria")
    resposta = cliente.post("/profissionais", json=dados_profissional())
    assert resposta.status_code == 201, resposta.text
    assert contar("auditoria") == antes + 1, "a escrita deveria gerar um registro"
    assert ultimo_registro("auditoria")["perfil"] == "desativada"


# Com a autenticação ativa, estes cenários verificam as credenciais.

def test_e2_sem_cabecalho_retorna_401(autenticacao_ativa):
    """E2 — Retorne 401 quando o cabeçalho de autenticação estiver ausente."""
    resposta = autenticacao_ativa["cliente"].get("/profissionais")
    assert resposta.status_code == 401
    assert "detail" in resposta.json()


def test_e2_chave_invalida_retorna_403(autenticacao_ativa):
    """E2 — Retorne 403 quando a chave informada não for reconhecida."""
    resposta = autenticacao_ativa["cliente"].get(
        "/profissionais", headers={"X-Auth-Key": "chave-que-nao-existe"})
    assert resposta.status_code == 403
    assert "detail" in resposta.json()


def test_e2_chave_de_coordenador_permite_acesso(autenticacao_ativa):
    """E2 — Permita o acesso com uma chave válida de coordenador."""
    resposta = autenticacao_ativa["cliente"].get(
        "/profissionais", headers=autenticacao_ativa["coordenador"])
    assert resposta.status_code == 200


def test_e2_saude_permanece_publica(autenticacao_ativa):
    """E2 — Mantenha `GET /saude` acessível mesmo sem cabeçalho."""
    resposta = autenticacao_ativa["cliente"].get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


# Os cenários seguintes diferenciam as permissões de cada perfil.

def test_e2_profissional_nao_cadastra_profissional(autenticacao_ativa):
    """E2 — Restrinja o cadastro de profissionais ao perfil coordenador."""
    resposta = autenticacao_ativa["cliente"].post(
        "/profissionais", json=dados_profissional(),
        headers=autenticacao_ativa["profissional"])
    assert resposta.status_code == 403


def test_e2_coordenador_cadastra_profissional(autenticacao_ativa):
    """E2 — Permita que o coordenador cadastre profissionais."""
    resposta = autenticacao_ativa["cliente"].post(
        "/profissionais", json=dados_profissional(),
        headers=autenticacao_ativa["coordenador"])
    assert resposta.status_code == 201, resposta.text
    checar_invariantes()


def test_e2_profissional_nao_cria_turno(autenticacao_ativa):
    """E2 — Exija o perfil coordenador para criar um turno."""
    resposta = autenticacao_ativa["cliente"].post("/turnos", json={
        "data_inicio": momento(350, 8), "data_fim": momento(350, 16),
        "especialidade_id": autenticacao_ativa["especialidade_id"],
        "cobertura_minima": 1},
        headers=autenticacao_ativa["profissional"])
    assert resposta.status_code == 403


def test_e2_profissional_acessa_rota_permitida(autenticacao_ativa):
    """E2 — Aceite a chave de profissional nas rotas sem restrição de perfil."""
    resposta = autenticacao_ativa["cliente"].get(
        "/turnos", headers=autenticacao_ativa["profissional"])
    assert resposta.status_code == 200


# Por fim, estes cenários observam o registro de auditoria.

def test_e2_escrita_gera_registro(autenticacao_ativa):
    """E2 — Gere um registro de auditoria, com o perfil da chave, para cada escrita."""
    antes = contar("auditoria")
    resposta = autenticacao_ativa["cliente"].post(
        "/profissionais", json=dados_profissional(),
        headers=autenticacao_ativa["coordenador"])
    assert resposta.status_code == 201, resposta.text
    assert contar("auditoria") == antes + 1, "a escrita deveria gerar um registro"
    assert ultimo_registro("auditoria")["perfil"] == "coordenador"


def test_e2_escrita_negada_por_perfil_gera_registro(autenticacao_ativa):
    """E2 — Registre também a escrita recusada por falta de permissão.

    A E2 exige registro para toda escrita, inclusive as que terminam em 4xx, e
    o perfil da chave utilizada. Uma escrita de profissional em rota de
    coordenador termina em 403 e deve gerar registro com perfil `profissional`.

    Este teste substitui `test_e2_leitura_nao_gera_registro`, da versão 1: a
    E2 exige registro das escritas, mas não proíbe registrar leituras.
    """
    antes = contar("auditoria")
    resposta = autenticacao_ativa["cliente"].post(
        "/profissionais", json=dados_profissional(),
        headers=autenticacao_ativa["profissional"])
    assert resposta.status_code == 403
    assert contar("auditoria") == antes + 1, "a escrita recusada deveria gerar um registro"
    registro = ultimo_registro("auditoria")
    assert registro["perfil"] == "profissional"
    assert numero(registro["codigo_resposta"]) == 403


def test_e2_escrita_recusada_tambem_gera_registro(autenticacao_ativa):
    """E2 — Registre também as escritas recusadas com resposta 4xx.

    O requisito torna a auditoria independente do resultado da operação.
    """
    antes = contar("auditoria")
    recusada = autenticacao_ativa["cliente"].post(
        "/profissionais",
        json={"nome": "", "email": "invalido", "carga_semanal": 99},
        headers=autenticacao_ativa["coordenador"])
    assert recusada.status_code == 422
    assert contar("auditoria") == antes + 1, "a escrita recusada deveria gerar um registro"
    assert numero(ultimo_registro("auditoria")["codigo_resposta"]) == 422


def test_e2_registro_contem_os_campos_exigidos(autenticacao_ativa):
    """E2 — Grave o registro com todos os campos previstos para a auditoria.

    Uma escrita gera exatamente um registro: o próprio registro de auditoria
    não gera outro. Os valores são conferidos sem exigir formato que a E2 não
    fixa: método sem distinção de caixa, caminho contido no valor gravado,
    código comparado como número e instante interpretável em ISO 8601.
    """
    exigidas = {"id", "metodo", "caminho", "perfil", "codigo_resposta", "instante"}
    faltantes = exigidas - colunas("auditoria")
    assert not faltantes, f"colunas ausentes na tabela auditoria: {sorted(faltantes)}"

    antes = contar("auditoria")
    resposta = autenticacao_ativa["cliente"].post(
        "/profissionais", json=dados_profissional(),
        headers=autenticacao_ativa["coordenador"])
    assert resposta.status_code == 201, resposta.text
    assert contar("auditoria") == antes + 1, (
        "a operacao de escrita deveria ter gerado exatamente um registro")

    registro = ultimo_registro("auditoria")
    assert str(registro["metodo"]).upper() == "POST"
    assert "/profissionais" in str(registro["caminho"])
    assert numero(registro["codigo_resposta"]) == 201
    assert registro["perfil"] == "coordenador"
    assert registro["instante"] is not None
    _converter_data_hora(registro["instante"])


def test_e2_auditoria_restrita_ao_coordenador(autenticacao_ativa):
    """E2 — Restrinja `GET /auditoria` ao coordenador com autenticação ativa."""
    resposta = autenticacao_ativa["cliente"].get(
        "/auditoria", headers=autenticacao_ativa["profissional"])
    assert resposta.status_code == 403
