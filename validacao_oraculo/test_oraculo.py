"""Valida o oráculo responsável pelas invariantes.

Os cenários positivos, negativos e de fronteira são montados sem depender da
aplicação avaliada. Cada um compara o conjunto exato de invariantes violadas,
não apenas a presença da violação esperada, e assim revela efeitos adicionais.

Antes do congelamento, execute `pytest validacao_oraculo/ -q` e confirme que o
comando termina com código de saída zero.
"""

import importlib
import os
import sqlite3

import pytest

SCHEMA = """
CREATE TABLE profissionais (id INTEGER PRIMARY KEY, nome TEXT, email TEXT,
  carga_semanal INTEGER, ativo INTEGER, horas_extras REAL);
CREATE TABLE especialidades (id INTEGER PRIMARY KEY, nome TEXT);
CREATE TABLE profissional_especialidade (profissional_id INTEGER, especialidade_id INTEGER);
CREATE TABLE turnos (id INTEGER PRIMARY KEY, data_inicio TEXT, data_fim TEXT,
  especialidade_id INTEGER, cobertura_minima INTEGER);
CREATE TABLE plantoes (id INTEGER PRIMARY KEY, turno_id INTEGER,
  profissional_id INTEGER, estado TEXT);
CREATE TABLE trocas (id INTEGER PRIMARY KEY, plantao_origem_id INTEGER,
  plantao_destino_id INTEGER, estado TEXT, data_solicitacao TEXT, data_decisao TEXT);
CREATE TABLE substituicoes (id INTEGER PRIMARY KEY, turno_id INTEGER,
  profissional_id INTEGER, posicao INTEGER, estado TEXT);
CREATE TABLE ausencias (id INTEGER PRIMARY KEY, profissional_id INTEGER,
  data_inicio TEXT, data_fim TEXT, tipo TEXT);
"""


@pytest.fixture
def banco(tmp_path):
    """Entregue a cada cenário uma base nova, sem dependência entre os casos."""
    caminho = tmp_path / "cenario.db"
    conexao = sqlite3.connect(caminho)
    conexao.executescript(SCHEMA)
    conexao.execute("INSERT INTO especialidades VALUES (1, 'Clinica')")
    conexao.execute("INSERT INTO especialidades VALUES (2, 'Pediatria')")
    conexao.execute("INSERT INTO profissionais VALUES (1,'Ana','ana@x.com',44,1,0)")
    conexao.execute("INSERT INTO profissionais VALUES (2,'Bruno','bruno@x.com',44,1,0)")
    conexao.execute("INSERT INTO profissional_especialidade VALUES (1,1)")
    conexao.execute("INSERT INTO profissional_especialidade VALUES (2,1)")
    os.environ["DATABASE_URL"] = f"sqlite:///{caminho}"
    yield conexao
    conexao.close()


def turno(conexao, tid, inicio, fim, especialidade=1, cobertura=1):
    conexao.execute("INSERT INTO turnos VALUES (?,?,?,?,?)",
                    (tid, inicio, fim, especialidade, cobertura))


def plantao(conexao, pid, tid, profissional):
    conexao.execute("INSERT INTO plantoes VALUES (?,?,?,'confirmado')",
                    (pid, tid, profissional))


def violadas(conexao) -> set:
    conexao.commit()
    import oracle.invariantes as invariantes
    importlib.reload(invariantes)
    return set(invariantes.verificar()["violadas"])


# O cenário positivo confirma o comportamento sem violações.

def test_cenario_valido_nao_viola_nada(banco):
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    plantao(banco, 1, 1, 1)
    assert violadas(banco) == set()


def test_banco_sem_dados_nao_viola_nada(banco):
    assert violadas(banco) == set()


def test_banco_inexistente_e_nao_avaliavel(tmp_path):
    """Não confunda a ausência do banco com invariantes satisfeitas."""
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'nao_existe.db'}"
    import oracle.invariantes as invariantes
    importlib.reload(invariantes)
    resultado = invariantes.verificar()
    assert resultado["avaliavel"] is False
    assert resultado["motivo"] == "banco_inexistente"
    assert all(resultado[f"inv{n}"] is None for n in range(1, 9))


# Os cenários de INV1 delimitam a sobreposição de intervalos.

def test_inv1_intervalos_adjacentes_nao_sobrepoem(banco):
    """Aceite a fronteira em que um plantão começa quando o anterior termina."""
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    turno(banco, 2, "2026-09-08T03:00:00", "2026-09-08T09:00:00")
    plantao(banco, 1, 1, 1)
    plantao(banco, 2, 2, 1)
    assert violadas(banco) == set()


def test_inv1_sobreposicao_de_um_minuto(banco):
    """Considere sobreposição mesmo quando a interseção durar apenas um minuto.

    Somente INV1 deve aparecer. INV2 percorre apenas pares sem sobreposição,
    pois registrar as duas invariantes contaria duas vezes o mesmo defeito.
    """
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    turno(banco, 2, "2026-09-07T15:59:00", "2026-09-07T20:00:00")
    plantao(banco, 1, 1, 1)
    plantao(banco, 2, 2, 1)
    assert violadas(banco) == {"inv1"}


def test_inv1_sobreposicao_entre_profissionais_distintos_e_valida(banco):
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00", cobertura=2)
    plantao(banco, 1, 1, 1)
    plantao(banco, 2, 1, 2)
    assert violadas(banco) == set()


# INV2 é exercitada nas fronteiras do descanso mínimo.

def test_inv2_descanso_de_exatamente_11h_e_valido(banco):
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    turno(banco, 2, "2026-09-08T03:00:00", "2026-09-08T09:00:00")
    plantao(banco, 1, 1, 1)
    plantao(banco, 2, 2, 1)
    assert violadas(banco) == set()


def test_inv2_descanso_de_10h59min_e_invalido(banco):
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    turno(banco, 2, "2026-09-08T02:59:00", "2026-09-08T09:00:00")
    plantao(banco, 1, 1, 1)
    plantao(banco, 2, 2, 1)
    assert violadas(banco) == {"inv2"}


# INV3 é exercitada ao redor do teto semanal.

def test_inv3_exatamente_44h_e_valido(banco):
    """Aceite 44 horas semanais, mas sinalize qualquer valor acima da fronteira."""
    banco.execute("UPDATE profissionais SET carga_semanal=44 WHERE id=1")
    for i, dia in enumerate([7, 9, 11, 13], start=1):
        turno(banco, i, f"2026-09-{dia:02d}T06:00:00", f"2026-09-{dia:02d}T17:00:00")
        plantao(banco, i, i, 1)  # Quatro plantões de 11 horas fecham 44 horas.
    assert violadas(banco) == set()


def test_inv3_44h_e_meia_hora_e_invalido(banco):
    banco.execute("UPDATE profissionais SET carga_semanal=44 WHERE id=1")
    for i, dia in enumerate([7, 9, 11], start=1):
        turno(banco, i, f"2026-09-{dia:02d}T06:00:00", f"2026-09-{dia:02d}T17:00:00")
        plantao(banco, i, i, 1)  # Até aqui, o total acumulado é de 33 horas.
    turno(banco, 4, "2026-09-13T06:00:00", "2026-09-13T17:30:00")  # O total chega a 44,5 horas.
    plantao(banco, 4, 4, 1)
    assert violadas(banco) == {"inv3", "inv8"}


def test_inv3_rateio_na_virada_de_semana(banco):
    """Divida entre as semanas as horas do plantão de domingo para segunda."""
    banco.execute("UPDATE profissionais SET carga_semanal=44, horas_extras=0 WHERE id=1")
    turno(banco, 1, "2026-09-13T20:00:00", "2026-09-14T04:00:00")
    plantao(banco, 1, 1, 1)
    assert violadas(banco) == set()


# INV4 verifica a compatibilidade de especialidades.

def test_inv4_especialidade_incompativel(banco):
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00", especialidade=2)
    plantao(banco, 1, 1, 1)  # Ana está vinculada apenas à especialidade Clínica.
    assert violadas(banco) == {"inv4"}


# INV5 cobre a sobreposição entre plantões e ausências.

def test_inv5_ausencia_adjacente_nao_sobrepoe(banco):
    """Aceite a ausência que termina exatamente quando o plantão começa."""
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    plantao(banco, 1, 1, 1)
    banco.execute("INSERT INTO ausencias VALUES "
                  "(1,1,'2026-09-05T00:00:00','2026-09-07T08:00:00','folga')")
    assert violadas(banco) == set()


def test_inv5_ausencia_sobreposta(banco):
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    plantao(banco, 1, 1, 1)
    banco.execute("INSERT INTO ausencias VALUES "
                  "(1,1,'2026-09-06T00:00:00','2026-09-09T00:00:00','ferias')")
    assert violadas(banco) == {"inv5"}


# INV6 observa a continuidade das posições na fila.

@pytest.mark.parametrize("posicoes,esperado", [
    ([], set()),
    ([1], set()),
    ([1, 2, 3], set()),
    ([1, 3], {"inv6"}),
    ([1, 2, 2], {"inv6"}),
    ([2, 3], {"inv6"}),
])
def test_inv6_formato_da_fila(banco, posicoes, esperado):
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    for i, posicao in enumerate(posicoes, start=1):
        banco.execute("INSERT INTO substituicoes VALUES (?,1,1,?,'aguardando')",
                      (i, posicao))
    assert violadas(banco) == esperado


def test_inv6_ignora_estados_diferentes_de_aguardando(banco):
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    banco.execute("INSERT INTO substituicoes VALUES (1,1,1,1,'aguardando')")
    banco.execute("INSERT INTO substituicoes VALUES (2,1,2,7,'cancelada')")
    assert violadas(banco) == set()


# INV7 começa pelos limites de dias consecutivos.

def test_inv7_seis_dias_consecutivos_e_valido(banco):
    banco.execute("UPDATE profissionais SET carga_semanal=44 WHERE id=1")
    for i, dia in enumerate(range(7, 13), start=1):  # Seis dias ainda são válidos.
        turno(banco, i, f"2026-09-{dia:02d}T08:00:00", f"2026-09-{dia:02d}T12:00:00")
        plantao(banco, i, i, 1)
    assert violadas(banco) == set()


def test_inv7_sete_dias_consecutivos_e_invalido(banco):
    banco.execute("UPDATE profissionais SET carga_semanal=44 WHERE id=1")
    for i, dia in enumerate(range(7, 14), start=1):  # O sétimo dia viola o limite.
        turno(banco, i, f"2026-09-{dia:02d}T08:00:00", f"2026-09-{dia:02d}T12:00:00")
        plantao(banco, i, i, 1)
    assert violadas(banco) == {"inv7"}


def test_inv7_dias_alternados_nao_violam(banco):
    banco.execute("UPDATE profissionais SET carga_semanal=44 WHERE id=1")
    for i, dia in enumerate([7, 9, 11, 13, 15, 17, 19], start=1):
        turno(banco, i, f"2026-09-{dia:02d}T08:00:00", f"2026-09-{dia:02d}T12:00:00")
        plantao(banco, i, i, 1)
    assert violadas(banco) == set()


# INV8 compara o total persistido com as horas extras calculadas.

def test_inv8_sem_excedente(banco):
    banco.execute("UPDATE profissionais SET carga_semanal=44, horas_extras=0 WHERE id=1")
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    plantao(banco, 1, 1, 1)
    assert violadas(banco) == set()


def test_inv8_excedente_registrado_corretamente(banco):
    banco.execute("UPDATE profissionais SET carga_semanal=20, horas_extras=10 WHERE id=1")
    for i, dia in enumerate([7, 9, 11], start=1):
        turno(banco, i, f"2026-09-{dia:02d}T08:00:00", f"2026-09-{dia:02d}T18:00:00")
        plantao(banco, i, i, 1)  # Trinta horas com carga 20 geram dez extras.
    assert violadas(banco) == set()


def test_inv8_valor_registrado_menor_que_o_esperado(banco):
    banco.execute("UPDATE profissionais SET carga_semanal=20, horas_extras=0 WHERE id=1")
    for i, dia in enumerate([7, 9, 11], start=1):
        turno(banco, i, f"2026-09-{dia:02d}T08:00:00", f"2026-09-{dia:02d}T18:00:00")
        plantao(banco, i, i, 1)
    assert violadas(banco) == {"inv8"}


def test_inv8_valor_registrado_maior_que_o_esperado(banco):
    banco.execute("UPDATE profissionais SET carga_semanal=20, horas_extras=99 WHERE id=1")
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T18:00:00")
    plantao(banco, 1, 1, 1)
    assert violadas(banco) == {"inv8"}


def test_inv8_excedente_em_duas_semanas(banco):
    banco.execute("UPDATE profissionais SET carga_semanal=20, horas_extras=20 WHERE id=1")
    for i, dia in enumerate([7, 9, 11], start=1):  # Primeira semana: dez extras.
        turno(banco, i, f"2026-09-{dia:02d}T08:00:00", f"2026-09-{dia:02d}T18:00:00")
        plantao(banco, i, i, 1)
    for i, dia in enumerate([14, 16, 18], start=4):  # Segunda semana: mais dez extras.
        turno(banco, i, f"2026-09-{dia:02d}T08:00:00", f"2026-09-{dia:02d}T18:00:00")
        plantao(banco, i, i, 1)
    assert violadas(banco) == set()


def test_inv8_plantao_cancelado_nao_conta(banco):
    banco.execute("UPDATE profissionais SET carga_semanal=20, horas_extras=0 WHERE id=1")
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T18:00:00")
    banco.execute("INSERT INTO plantoes VALUES (1,1,1,'cancelado')")
    assert violadas(banco) == set()

# Estes cenários de INV7 tratam dos plantões que atravessam a meia-noite.

def test_inv7_plantao_noturno_conta_nos_dois_dias(banco):
    """Conte sete datas civis em seis plantões noturnos das 22h às 02h.

    Pela especificação, cada plantão que atravessa a meia-noite toca os dois
    dias. Considerar apenas a data inicial registraria seis dias e esconderia a
    violação.
    """
    banco.execute("UPDATE profissionais SET carga_semanal=44 WHERE id=1")
    # Todos começam entre os dias 7 e 12 e terminam no dia seguinte.
    for i, dia in enumerate(range(7, 13), start=1):
        turno(banco, i, f"2026-09-{dia:02d}T22:00:00", f"2026-09-{dia + 1:02d}T02:00:00")
        plantao(banco, i, i, 1)
    assert violadas(banco) == {"inv7"}


def test_inv7_cinco_plantoes_noturnos_tocam_seis_dias(banco):
    """Aceite cinco plantões noturnos que, juntos, alcançam seis datas."""
    banco.execute("UPDATE profissionais SET carga_semanal=44 WHERE id=1")
    for i, dia in enumerate(range(7, 12), start=1):
        turno(banco, i, f"2026-09-{dia:02d}T22:00:00", f"2026-09-{dia + 1:02d}T02:00:00")
        plantao(banco, i, i, 1)
    assert violadas(banco) == set()


def test_inv7_termino_exato_a_meia_noite_nao_toca_o_dia_seguinte(banco):
    """Não conte o dia seguinte quando o plantão terminar exatamente às 00:00.

    Nesse caso não existe duração positiva após a meia-noite, portanto o novo
    dia não faz parte do intervalo trabalhado.
    """
    banco.execute("UPDATE profissionais SET carga_semanal=44 WHERE id=1")
    for i, dia in enumerate(range(7, 14), start=1):  # Todos terminam à meia-noite.
        turno(banco, i, f"2026-09-{dia:02d}T20:00:00", f"2026-09-{dia + 1:02d}T00:00:00")
        plantao(banco, i, i, 1)
    # As datas de 7 a 13 completam sete dias e violam INV7.
    assert violadas(banco) == {"inv7"}


# O último cenário de INV5 mistura formatos de data equivalentes.

@pytest.mark.parametrize("formato", [
    "2026-09-07T10:00:00",
    "2026-09-07 10:00:00.000000",
    "2026-09-07 10:00:00",
])
def test_inv5_independe_do_formato_textual(banco, formato):
    """Detecte a sobreposição mesmo quando as datas usam serializações diferentes.

    Componentes diferentes podem gravar o mesmo instante de maneiras distintas,
    e a ordenação textual do SQLite não preserva necessariamente a cronologia
    entre esses formatos.
    """
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    plantao(banco, 1, 1, 1)
    fim = formato.replace("10:00:00", "12:00:00")
    banco.execute("INSERT INTO ausencias VALUES (1,1,?,?,'atestado')",
                  (formato, fim))
    assert violadas(banco) == {"inv5"}


# Cenários acrescentados na versão 2 do oráculo.

def test_inv2_detectada_mesmo_com_sobreposicao_entre_outros_plantoes(banco):
    """Registre INV2 quando o descanso curto não ocorre entre vizinhos por início.

    O plantão 1 (00h–10h) sobrepõe o 2 (01h–05h), o que viola INV1. O plantão
    3 começa às 17h: há 12 horas depois do plantão 2, mas só 7 horas depois do
    plantão 1. A versão 1 comparava apenas vizinhos na ordem de início (1–2 e
    2–3) e não registrava esta violação de INV2.
    """
    turno(banco, 1, "2026-09-07T00:00:00", "2026-09-07T10:00:00")
    turno(banco, 2, "2026-09-07T01:00:00", "2026-09-07T05:00:00")
    turno(banco, 3, "2026-09-07T17:00:00", "2026-09-07T21:00:00")
    plantao(banco, 1, 1, 1)
    plantao(banco, 2, 2, 1)
    plantao(banco, 3, 3, 1)
    assert violadas(banco) == {"inv1", "inv2"}


def test_inv2_sem_sobreposicao_mantem_o_resultado_da_versao_1(banco):
    """Sem sobreposição, a verificação nova coincide com a comparação entre vizinhos."""
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T12:00:00")
    turno(banco, 2, "2026-09-08T08:00:00", "2026-09-08T12:00:00")
    turno(banco, 3, "2026-09-08T20:00:00", "2026-09-09T00:00:00")
    plantao(banco, 1, 1, 1)
    plantao(banco, 2, 2, 1)
    plantao(banco, 3, 3, 1)
    assert violadas(banco) == {"inv2"}


@pytest.mark.parametrize("inicio,fim", [
    ("2026-09-07T10:00:00+00:00", "2026-09-07T12:00:00+00:00"),
    ("2026-09-07T10:00:00Z", "2026-09-07T12:00:00Z"),
    ("2026-09-07T07:00:00-03:00", "2026-09-07T09:00:00-03:00"),
])
def test_inv5_datas_com_fuso_sao_convertidas_para_utc(banco, inicio, fim):
    """Converta para UTC as datas gravadas com fuso antes de compará-las.

    10h–12h UTC coincide com o plantão das 8h às 16h, também em UTC, qualquer
    que seja a forma de escrita. A versão 1 apenas descartava o fuso: o
    terceiro caso viraria 07h–09h e a sobreposição ainda existiria por acaso,
    mas um deslocamento maior a esconderia.
    """
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    plantao(banco, 1, 1, 1)
    banco.execute("INSERT INTO ausencias VALUES (1,1,?,?,'folga')", (inicio, fim))
    assert violadas(banco) == {"inv5"}


def test_inv5_fuso_que_desloca_para_fora_do_plantao(banco):
    """Não acuse sobreposição quando, convertida para UTC, a ausência fica fora do plantão.

    14h–15h em UTC-03:00 corresponde a 17h–18h UTC, depois do plantão das 8h às
    16h. Descartar o fuso, como na versão 1, criaria uma violação inexistente.
    """
    turno(banco, 1, "2026-09-07T08:00:00", "2026-09-07T16:00:00")
    plantao(banco, 1, 1, 1)
    banco.execute("INSERT INTO ausencias VALUES (1,1,?,?,'folga')",
                  ("2026-09-07T14:00:00-03:00", "2026-09-07T15:00:00-03:00"))
    assert violadas(banco) == set()
