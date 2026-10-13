"""Verifica as oito invariantes definidas para o Sistema de Escala de Plantão.

O oráculo lê o SQLite diretamente, seguindo o esquema fixado na seção 2.1 da
especificação. Assim, a aplicação observada não participa da própria avaliação.

As regras temporais são as estabelecidas na seção 4.1 da especificação:
intervalos semiabertos, semana iniciada na segunda-feira às 00:00 UTC e
rateio proporcional de plantões que atravessam a virada de semana.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

DESCANSO_MINIMO_H = 11
TETO_SEMANAL_H = 44
DIAS_CONSECUTIVOS_MAX = 6


# A leitura direta do banco mantém a avaliação independente. Todas as
# verificações acontecem em memória, sem alterar os dados observados.
def _caminho_banco() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///./escala.db")
    return url.replace("sqlite:///", "").replace("sqlite://", "")


def _conexao():
    conexao = sqlite3.connect(_caminho_banco())
    conexao.row_factory = sqlite3.Row
    return conexao


def _converter_data_hora(valor) -> datetime:
    """Converta o valor gravado em `datetime` ingênuo, expresso em UTC.

    Um valor com fuso explícito é primeiro convertido para UTC. Apenas remover
    o fuso deslocaria o instante sempre que o deslocamento não fosse zero.
    """
    if isinstance(valor, datetime):
        data_hora = valor
    else:
        texto = str(valor).replace("Z", "+00:00")
        data_hora = datetime.fromisoformat(texto)
    if data_hora.tzinfo is not None:
        data_hora = data_hora.astimezone(timezone.utc)
    return data_hora.replace(tzinfo=None)


def _plantoes_confirmados(conexao) -> list[dict]:
    linhas = conexao.execute("""
        SELECT p.id, p.profissional_id, t.id AS turno_id,
               t.data_inicio, t.data_fim, t.especialidade_id
        FROM plantoes p JOIN turnos t ON t.id = p.turno_id
        WHERE p.estado = 'confirmado'
    """).fetchall()
    return [{"id": linha["id"], "profissional_id": linha["profissional_id"],
             "turno_id": linha["turno_id"],
             "inicio": _converter_data_hora(linha["data_inicio"]),
             "fim": _converter_data_hora(linha["data_fim"]),
             "especialidade_id": linha["especialidade_id"]} for linha in linhas]


def _por_profissional(plantoes) -> dict[int, list[dict]]:
    mapa: dict[int, list[dict]] = {}
    for plantao in plantoes:
        mapa.setdefault(plantao["profissional_id"], []).append(plantao)
    for lista in mapa.values():
        lista.sort(key=lambda plantao: plantao["inicio"])
    return mapa


def _dias_trabalhados(plantao) -> list:
    """Identifique as datas civis alcançadas por um plantão.

    Segundo a seção 4.1 da especificação, um plantão que atravessa a meia-noite
    conta como trabalho nos dois dias quando há duração positiva em ambos.
    Olhar somente para a data de início reduziria indevidamente a contagem de
    dias consecutivos.

    Subtrair um microssegundo preserva a natureza semiaberta do intervalo: se
    o plantão termina exatamente às 00:00, o dia seguinte não é contado.
    """
    ultimo_instante = plantao["fim"] - timedelta(microseconds=1)
    atual, ultimo = plantao["inicio"].date(), ultimo_instante.date()
    dias = []
    while atual <= ultimo:
        dias.append(atual)
        atual += timedelta(days=1)
    return dias


def _inicio_semana(momento: datetime) -> datetime:
    dia = momento - timedelta(days=momento.weekday())
    return dia.replace(hour=0, minute=0, second=0, microsecond=0)


def _horas_por_semana(plantoes) -> dict[datetime, float]:
    """Distribua entre as semanas as horas dos plantões que cruzam seus limites."""
    semanas: dict[datetime, float] = {}
    for plantao in plantoes:
        inicio, fim = plantao["inicio"], plantao["fim"]
        cursor = inicio
        while cursor < fim:
            limite_semana = _inicio_semana(cursor) + timedelta(days=7)
            trecho_fim = min(fim, limite_semana)
            horas = (trecho_fim - cursor).total_seconds() / 3600
            chave = _inicio_semana(cursor)
            semanas[chave] = semanas.get(chave, 0.0) + horas
            cursor = trecho_fim
    return semanas


def verificar() -> dict:
    """Verifique as oito invariantes lendo diretamente o banco.

    Quando o banco ainda não existe, a função devolve uma lista vazia de
    violações e registra a condição nos detalhes. A ausência de dados, portanto,
    não é confundida com uma falha do próprio oráculo.
    """
    caminho = _caminho_banco()
    if not os.path.exists(caminho):
    # A falta do banco não prova que as invariantes foram preservadas; apenas
    # indica que não foi possível avaliá-las. Marcá-las como satisfeitas faria
    # uma aplicação incapaz de iniciar parecer inteiramente correta.
        return {**{f"inv{numero_invariante}": None
                   for numero_invariante in range(1, 9)},
                "avaliavel": False, "motivo": "banco_inexistente",
                "violadas": [], "detalhes": ["NAO AVALIAVEL: banco inexistente"],
                "assinaturas": []}

    conexao = _conexao()
    resultado = {f"inv{numero_invariante}": True
                 for numero_invariante in range(1, 9)}
    detalhes: list[str] = []

    plantoes = _plantoes_confirmados(conexao)
    por_profissional = _por_profissional(plantoes)

    # INV1 trata da sobreposição de plantões. Como os plantões de cada
    # profissional estão ordenados pelo início, basta comparar vizinhos: há
    # sobreposição quando o próximo começa antes do término do anterior. Como
    # os intervalos são semiabertos, terminar e começar no mesmo instante é válido.
    for profissional_id, lista in por_profissional.items():
        for plantao_anterior, plantao_atual in zip(lista, lista[1:]):
            if plantao_atual["inicio"] < plantao_anterior["fim"]:
                resultado["inv1"] = False
                detalhes.append(
                    f"inv1: prof {profissional_id} plantoes "
                    f"{plantao_anterior['id']} e {plantao_atual['id']}"
                )

    # INV2 exige ao menos 11 horas de descanso entre o fim de um plantão
    # confirmado e o início do plantão seguinte do mesmo profissional. Para
    # cada plantão, o seguinte é o que começa mais cedo entre os que começam
    # no fim dele ou depois. Pares sobrepostos ficam com INV1. A fronteira de
    # exatamente 11 horas é aceita, conforme a seção 4.1 da especificação.
    #
    # A versão 1 comparava apenas vizinhos na ordem de início. Sem
    # sobreposição o resultado é o mesmo; com sobreposição, um par sem
    # descanso podia ficar sem registro.
    for profissional_id, lista in por_profissional.items():
        for plantao_atual in lista:
            inicios_seguintes = [outro["inicio"] for outro in lista
                                 if outro is not plantao_atual
                                 and outro["inicio"] >= plantao_atual["fim"]]
            if not inicios_seguintes:
                continue
            intervalo = (min(inicios_seguintes)
                         - plantao_atual["fim"]).total_seconds() / 3600
            if intervalo < DESCANSO_MINIMO_H:
                resultado["inv2"] = False
                detalhes.append(
                    f"inv2: prof {profissional_id} intervalo {intervalo:.1f}h "
                    f"apos o plantao {plantao_atual['id']}"
                )

    # INV3 limita a jornada a 44 horas por semana, contada desde segunda-feira
    # às 00:00 UTC. `_horas_por_semana` reparte os plantões que atravessam essa
    # fronteira, e a tolerância de 1e-6 evita falsos positivos de ponto flutuante.
    for profissional_id, lista in por_profissional.items():
        for semana, horas in _horas_por_semana(lista).items():
            if horas > TETO_SEMANAL_H + 1e-6:
                resultado["inv3"] = False
                detalhes.append(
                    f"inv3: prof {profissional_id} semana {semana.date()} {horas:.1f}h"
                )

    # INV4 confere se cada plantão confirmado foi atribuído a alguém com a
    # especialidade exigida. Para isso, consulta a associação
    # `profissional_especialidade`; é a única invariante cadastral, não temporal.
    for plantao in plantoes:
        tem_especialidade = conexao.execute(
            "SELECT 1 FROM profissional_especialidade "
            "WHERE profissional_id=? AND especialidade_id=?",
            (plantao["profissional_id"], plantao["especialidade_id"])).fetchone()
        if not tem_especialidade:
            resultado["inv4"] = False
            detalhes.append(f"inv4: plantao {plantao['id']} sem especialidade")

    # INV5 impede que um plantão confirmado coincida com uma ausência. A consulta
    # traduz a sobreposição de intervalos semiabertos: a ausência começa antes do
    # fim do plantão e termina depois de seu início.
    #
    # A comparação usa objetos `datetime`, não texto do SQLite. A mesma data pode
    # ser serializada como "2026-09-07T10:00:00" ou
    # "2026-09-07 10:00:00.000000", cuja ordem alfabética não representa com
    # segurança a ordem cronológica.
    ausencias_por_profissional: dict[int, list] = {}
    for linha in conexao.execute(
            "SELECT profissional_id, data_inicio, data_fim FROM ausencias"):
        ausencias_por_profissional.setdefault(linha["profissional_id"], []).append(
            (_converter_data_hora(linha["data_inicio"]),
             _converter_data_hora(linha["data_fim"])))

    for plantao in plantoes:
        conflito = any(
            inicio_ausencia < plantao["fim"] and fim_ausencia > plantao["inicio"]
            for inicio_ausencia, fim_ausencia
            in ausencias_por_profissional.get(plantao["profissional_id"], []))
        if conflito:
            resultado["inv5"] = False
            detalhes.append(f"inv5: plantao {plantao['id']} sobrepoe ausencia")
            
    # INV6 pede que as posições em estado `aguardando` formem 1, 2, 3... sem
    # lacunas ou repetições. A comparação com `range` revela tanto cancelamentos
    # sem reordenação quanto posições duplicadas. Outros estados ficam de fora.
    for linha in conexao.execute("SELECT DISTINCT turno_id FROM substituicoes"):
        posicoes = [registro["posicao"] for registro in conexao.execute(
            "SELECT posicao FROM substituicoes WHERE turno_id=? "
            "AND estado='aguardando' ORDER BY posicao", (linha["turno_id"],))]
        if posicoes != list(range(1, len(posicoes) + 1)):
            resultado["inv6"] = False
            detalhes.append(f"inv6: turno {linha['turno_id']} fila {posicoes}")

    # INV7 limita o trabalho a seis dias civis seguidos. A verificação ordena os
    # dias distintos com plantão e aumenta a sequência quando dois vizinhos
    # diferem por um dia; qualquer intervalo maior reinicia a contagem.
    for profissional_id, lista in por_profissional.items():
        dias = sorted({dia for plantao in lista
                       for dia in _dias_trabalhados(plantao)})
        consecutivos = 1
        for anterior, atual in zip(dias, dias[1:]):
            consecutivos = consecutivos + 1 if (atual - anterior).days == 1 else 1
            if consecutivos > DIAS_CONSECUTIVOS_MAX:
                resultado["inv7"] = False
                detalhes.append(
                    f"inv7: prof {profissional_id} {consecutivos} dias seguidos"
                )
                break

    # INV8 compara `horas_extras` com a soma semanal das horas que ultrapassam a
    # carga do profissional. O recálculo a partir dos plantões confirmados revela
    # fluxos que deixaram de atualizar o campo derivado. Uma tolerância de 0,01
    # hora absorve arredondamentos sem esconder diferenças relevantes.
    for linha in conexao.execute(
            "SELECT id, carga_semanal, horas_extras FROM profissionais"):
        lista = por_profissional.get(linha["id"], [])
        esperado = sum(max(0.0, horas - linha["carga_semanal"])
                       for horas in _horas_por_semana(lista).values())
        registrado = float(linha["horas_extras"] or 0)
        if abs(esperado - registrado) > 0.01:
            resultado["inv8"] = False
            detalhes.append(f"inv8: prof {linha['id']} esperado {esperado:.2f}, "
                            f"registrado {registrado:.2f}")

    conexao.close()
    resultado["violadas"] = [
        chave_invariante
        for chave_invariante in (
            f"inv{numero_invariante}" for numero_invariante in range(1, 9)
        )
        if not resultado[chave_invariante]
    ]
    resultado["avaliavel"] = True
    resultado["motivo"] = ""
    resultado["detalhes"] = detalhes[:20]
    # Lista completa, usada pela suíte para separar as violações que cada
    # cenário introduz das que já estavam no banco (ver auxiliares.py).
    resultado["assinaturas"] = sorted(set(detalhes))
    return resultado
