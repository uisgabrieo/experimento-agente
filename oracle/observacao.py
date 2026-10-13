"""Observação de efeitos persistidos, pelo esquema obrigatório da especificação.

Regra da suíte: o corpo de uma resposta HTTP só é verificado quando a
especificação o define, como em RF04, RF10, RF23, RF29, RF37, RF38 e na rota de
auditoria da E2. Os demais efeitos, como estado de plantão, posição na fila,
horas extras e data de decisão, são lidos aqui, diretamente no SQLite.

A leitura direta é o mesmo mecanismo do oráculo de invariantes. Ela não executa
código da aplicação, não altera o estado observado e depende apenas dos nomes
de tabelas e colunas que a seção 2.1 da especificação torna obrigatórios. Para
a tabela `auditoria`, os nomes vêm do texto da E2.

A versão 1 da suíte observava esses efeitos pelo corpo das respostas e por
rotas que a especificação não define, como `GET /plantoes/{id}`. Uma
implementação aderente podia reprovar por isso, e foi o que ocorreu com o RF34.
"""

import os
import sqlite3
from contextlib import closing

# Somente estes nomes podem compor uma consulta. Eles vêm da seção 2.1 da
# especificação e do texto da E2, nunca de dados recebidos da aplicação.
TABELAS = frozenset({
    "profissionais", "especialidades", "profissional_especialidade", "turnos",
    "plantoes", "trocas", "substituicoes", "ausencias", "auditoria",
})


def _caminho_banco() -> str:
    """Resolva o arquivo SQLite a partir da mesma variável usada pelo oráculo."""
    url = os.environ.get("DATABASE_URL", "sqlite:///./escala.db")
    return url.replace("sqlite:///", "").replace("sqlite://", "")


def _consultar(sql, parametros=()):
    with closing(sqlite3.connect(_caminho_banco())) as conexao:
        conexao.row_factory = sqlite3.Row
        return [dict(registro) for registro in conexao.execute(sql, parametros)]


def _tabela(nome):
    if nome not in TABELAS:
        raise ValueError(f"tabela fora do esquema da especificacao: {nome}")
    return nome


def linha(tabela, identificador):
    """Devolva o registro com o `id` informado, ou None se ele não existir."""
    registros = _consultar(f"SELECT * FROM {_tabela(tabela)} WHERE id=?",
                           (identificador,))
    return registros[0] if registros else None


def contar(tabela):
    """Devolva a quantidade de registros da tabela."""
    return _consultar(f"SELECT COUNT(*) AS n FROM {_tabela(tabela)}")[0]["n"]


def ultimo_registro(tabela):
    """Devolva o registro inserido por último, pela ordem física do SQLite.

    `rowid` acompanha a ordem de inserção mesmo que `id` não seja inteiro.
    """
    registros = _consultar(
        f"SELECT * FROM {_tabela(tabela)} ORDER BY rowid DESC LIMIT 1")
    return registros[0] if registros else None


def colunas(tabela):
    """Devolva o conjunto de colunas existentes na tabela."""
    return {registro["name"] for registro in
            _consultar(f"PRAGMA table_info({_tabela(tabela)})")}


def verdadeiro(valor) -> bool:
    """Interprete um booleano gravado pelo SQLite (1/0, texto ou bool)."""
    return str(valor).strip().lower() in {"1", "true", "t"}


def estado_da_substituicao(substituicao_id):
    """Devolva o estado registrado da substituição, ou None se ela não existir."""
    registro = linha("substituicoes", substituicao_id)
    return registro["estado"] if registro else None


def posicoes_aguardando(turno_id):
    """Devolva (profissional, posição) das inscrições em espera, por posição."""
    registros = _consultar(
        "SELECT profissional_id, posicao FROM substituicoes "
        "WHERE turno_id=? AND estado='aguardando' ORDER BY posicao", (turno_id,))
    return [(registro["profissional_id"], registro["posicao"])
            for registro in registros]


def ids_aguardando_em_ordem(turno_id):
    """Devolva os ids das inscrições em espera, na ordem de `posicao`."""
    registros = _consultar(
        "SELECT id FROM substituicoes WHERE turno_id=? AND estado='aguardando' "
        "ORDER BY posicao", (turno_id,))
    return [registro["id"] for registro in registros]


def plantoes_confirmados(turno_id, profissional_id=None):
    """Devolva os plantões confirmados do turno, opcionalmente de uma pessoa."""
    consulta = ("SELECT id, profissional_id FROM plantoes "
                "WHERE turno_id=? AND estado='confirmado'")
    parametros = [turno_id]
    if profissional_id is not None:
        consulta += " AND profissional_id=?"
        parametros.append(profissional_id)
    return _consultar(consulta, parametros)


def vinculo_existe(profissional_id, especialidade_id) -> bool:
    """Informe se o profissional está vinculado à especialidade."""
    return bool(_consultar(
        "SELECT 1 FROM profissional_especialidade "
        "WHERE profissional_id=? AND especialidade_id=?",
        (profissional_id, especialidade_id)))


def horas_extras(profissional_id) -> float:
    """Devolva `horas_extras` como número; nulo vale zero, como no oráculo."""
    registro = linha("profissionais", profissional_id)
    assert registro is not None, f"profissional {profissional_id} nao consta no banco"
    return float(registro["horas_extras"] or 0)


def itens_da_fila(resposta):
    """Normalize o corpo devolvido pela rota do RF36.

    O RF36 determina o conteúdo e a ordenação da fila, mas não fixa o envelope
    `{itens, total}`, que a especificação exige apenas em RF04, RF10, RF23 e
    RF29. Uma implementação que devolva a lista diretamente é aderente.
    """
    corpo = resposta.json()
    if isinstance(corpo, dict):
        assert "itens" in corpo, f"corpo sem lista de itens: {corpo!r}"
        return corpo["itens"]
    assert isinstance(corpo, list), f"corpo inesperado na fila: {corpo!r}"
    return corpo
