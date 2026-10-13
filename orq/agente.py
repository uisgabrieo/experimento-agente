"""Define as interfaces usadas para executar o agente de codificação.

`AgenteClaudeCode` executa o agente real em modo não interativo.
`AgenteFalso` reproduz o fluxo sem consumir cota; serve apenas para validar o
orquestrador e nunca produz dados da pesquisa.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

# Textos que o Claude Code devolve quando o limite do plano é atingido.
SINAIS_DE_COTA = ("session limit", "usage limit", "limit reached", "rate limit",
                  "hit your", "resets ")
# Sinais inequívocos, usados para recusar como "sucesso" uma resposta curta que
# é só o aviso de limite (por exemplo, se o código de saída vier 0).
SINAIS_FORTES_DE_COTA = ("hit your session limit", "hit your usage limit",
                         "usage limit reached", "session limit reached")


@dataclass
class Resposta:
    texto: str
    segundos: float
    codigo_saida: int
    erro: str = ""
    bruto: str = ""
    metadados: dict = field(default_factory=dict)

    @property
    def sucesso(self) -> bool:
        if self.codigo_saida != 0 or self.metadados.get("is_error", False):
            return False
        # Aviso de limite devolvido como se fosse resposta não é resultado.
        texto = (self.texto or "").strip().lower()
        return not (len(texto) <= 400 and any(sinal in texto for sinal in SINAIS_FORTES_DE_COTA))

    @property
    def cota_esgotada(self) -> bool:
        texto = f"{self.texto}\n{self.erro}".lower()
        return any(sinal in texto for sinal in SINAIS_DE_COTA)


def interpretar_saida(saida: str) -> tuple[str, dict]:
    """Extraia o texto da resposta e os metadados de `--output-format json`.

    O formato JSON informa o modelo efetivamente usado, os tokens, o custo e se
    a execução terminou em erro. Se a saída não for o JSON esperado, o texto
    integral é mantido e nenhum metadado é inventado.
    """
    texto = (saida or "").strip()
    candidatos = [texto] + list(reversed(texto.splitlines()))
    for candidato in candidatos:
        try:
            dados = json.loads(candidato)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(dados, dict) or ("result" not in dados
                                           and dados.get("type") != "result"):
            continue
        uso = dados.get("usage") or {}
        modelos = dados.get("modelUsage") or {}
        meta = {
            "formato": "json",
            "subtipo": dados.get("subtype", ""),
            "is_error": bool(dados.get("is_error", False)),
            "num_turnos": dados.get("num_turns", ""),
            "duracao_ms": dados.get("duration_ms", ""),
            "custo_usd": dados.get("total_cost_usd", dados.get("cost_usd", "")),
            "tokens_entrada": uso.get("input_tokens", ""),
            "tokens_saida": uso.get("output_tokens", ""),
            "tokens_cache_criacao": uso.get("cache_creation_input_tokens", ""),
            "tokens_cache_leitura": uso.get("cache_read_input_tokens", ""),
            "modelos": ",".join(sorted(modelos)) if isinstance(modelos, dict) else "",
            "sessao": dados.get("session_id", ""),
        }
        return str(dados.get("result") or ""), meta
    return saida or "", {"formato": "texto"}


class AgenteBase:
    nome = "base"

    def executar(self, instrucao: str, pasta: Path) -> Resposta:
        raise NotImplementedError

    def versao(self) -> str:
        return self.nome


class AgenteClaudeCode(AgenteBase):
    """Executa o Claude Code em modo não interativo.

    `--permission-mode acceptEdits` permite editar arquivos sem confirmação
    humana, mas não executar comandos: o agente trabalha só a partir dos
    relatórios. Isso também impede que ele alcance, por terminal, a árvore da
    pesquisa onde estão o oráculo e as suítes.
    """

    nome = "claude-code"

    def __init__(self, timeout: int = 1800, modelo: str | None = None):
        self.timeout = timeout
        # O modelo é fixado explicitamente; o identificador efetivamente usado
        # em cada chamada fica registrado nos metadados da resposta.
        self.modelo = modelo or os.getenv("MODELO_AGENTE", "opus")

    def comando(self, instrucao: str) -> list[str]:
        comando = ["claude", "-p", instrucao, "--permission-mode", "acceptEdits",
                   "--output-format", "json"]
        if self.modelo:
            comando += ["--model", self.modelo]
        return comando

    def executar(self, instrucao: str, pasta: Path) -> Resposta:
        inicio = time.perf_counter()
        try:
            # UTF-8 com substituição: sem isso o Windows adota cp1252 e um
            # único caractere fora da tabela interrompe a leitura da saída.
            proc = subprocess.run(self.comando(instrucao), cwd=pasta,
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return Resposta(texto="", segundos=self.timeout, codigo_saida=124,
                            erro="tempo limite excedido")
        except FileNotFoundError:
            return Resposta(texto="", segundos=0, codigo_saida=127,
                            erro="comando 'claude' nao encontrado no PATH")
        except OSError as erro:
            return Resposta(texto="", segundos=time.perf_counter() - inicio,
                            codigo_saida=126, erro=f"falha ao iniciar o agente: {erro}")
        texto, meta = interpretar_saida(proc.stdout)
        resposta = Resposta(texto=texto, segundos=time.perf_counter() - inicio,
                            codigo_saida=proc.returncode,
                            erro=(proc.stderr or "").strip()[:2000],
                            bruto=proc.stdout or "", metadados=meta)
        if not resposta.sucesso and not resposta.erro:
            resposta.erro = texto.strip()[:2000]
        return resposta

    def versao(self) -> str:
        try:
            processo = subprocess.run(["claude", "--version"], capture_output=True,
                                      text=True, encoding="utf-8",
                                      errors="replace", timeout=30)
            # Primeira linha, como em manifesto.py: avisos em linhas seguintes
            # não podem fazer a comparação de versões falhar.
            return ((processo.stdout or processo.stderr or "").strip().splitlines()
                    or ["desconhecida"])[0]
        except Exception:  # pylint: disable=broad-except
            return "desconhecida"


class AgenteFalso(AgenteBase):
    """Simula o agente para validar o orquestrador, sem chamadas externas.

    Variáveis opcionais, usadas apenas em testes do próprio orquestrador:

    - `AGENTE_FALSO_FONTES`: JSON {"M0": pasta, "E1": pasta, "E2": pasta};
      a pasta `app/` indicada substitui a da área de trabalho na etapa;
    - `AGENTE_FALSO_FALHAS`: números das chamadas que devem falhar como se a
      cota tivesse acabado (ex.: "3,9").
    """

    nome = "falso"

    def __init__(self, semente: int = 42):
        self.aleatorio = random.Random(semente)
        self.chamadas = 0
        self.fontes = json.loads(os.getenv("AGENTE_FALSO_FONTES", "{}") or "{}")
        self.falhas = {int(numero) for numero in
                       os.getenv("AGENTE_FALSO_FALHAS", "").split(",") if numero.strip()}

    @staticmethod
    def _etapa(instrucao: str) -> str:
        if "RELATORIOS DE ANALISE" in instrucao:
            return "correcao"
        if "REQUISITO DE MUDANCA" not in instrucao:
            return "M0"
        requisito = instrucao.split("REQUISITO DE MUDANCA", 1)[1]
        return "E2" if "X-Auth-Key" in requisito else "E1"

    def executar(self, instrucao: str, pasta: Path) -> Resposta:
        self.chamadas += 1
        pasta = Path(pasta)
        etapa = self._etapa(instrucao)
        if self.chamadas in self.falhas:
            # Simula uma interrupção no meio do trabalho: deixa uma edição
            # parcial que o orquestrador precisa descartar.
            (pasta / "app").mkdir(parents=True, exist_ok=True)
            (pasta / "app" / "parcial_interrompido.py").write_text("x = 1\n", encoding="utf-8")
            return Resposta(texto="You've hit your session limit · resets 5am",
                            segundos=0.1, codigo_saida=1,
                            erro="You've hit your session limit · resets 5am",
                            metadados={"formato": "simulado", "is_error": True})
        fonte = self.fontes.get(etapa)
        if fonte:
            destino = pasta / "app"
            if destino.exists():
                shutil.rmtree(destino)
            shutil.copytree(Path(fonte) / "app", destino)
        elif etapa == "M0":
            self._gerar_inicial(pasta)
        elif etapa == "correcao":
            self._corrigir(pasta)
        else:
            self._evoluir(pasta)
        return Resposta(texto=f"simulado: {etapa}", segundos=0.1, codigo_saida=0,
                        metadados={"formato": "simulado", "modelos": "simulado"})

    def _gerar_inicial(self, pasta: Path):
        (pasta / "app").mkdir(parents=True, exist_ok=True)
        for indice_modulo in range(6):
            (pasta / "app" / f"modulo_{indice_modulo}.py").write_text(
                f"import os\nimport sys\n\n\ndef funcao_{indice_modulo}(valor):\n"
                + "".join(f"    if valor > {limite}:\n        valor += {limite}\n"
                          for limite in range(6))
                + "    return valor\n", encoding="utf-8")

    def _corrigir(self, pasta: Path):
        for arq in sorted((pasta / "app").glob("*.py")):
            texto = arq.read_text(encoding="utf-8")
            if "import sys" in texto and self.aleatorio.random() < 0.7:
                texto = texto.replace("import sys\n", "")
            if '"""' not in texto:
                texto = '"""Modulo do sistema."""\n' + texto
            arq.write_text(texto, encoding="utf-8")

    def _evoluir(self, pasta: Path):
        quantidade_modulos = len(list((pasta / "app").glob("*.py")))
        (pasta / "app" / f"extra_{quantidade_modulos}.py").write_text(
            '"""Modulo acrescentado."""\n\n\ndef nova_funcao():\n    return True\n',
            encoding="utf-8")
