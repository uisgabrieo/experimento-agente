"""Executa as etapas da coleta 2 (instrumento v2).

Uso (PowerShell, na pasta tcc-v2, com a venv ativa):
    python orquestrador.py --verificar-agente
    python orquestrador.py --repeticoes 1 --inicio 1
    python orquestrador.py --continuar --inicio 1 --repeticoes 1

Etapas de cada repetição:
    M0        geração com base na especificação congelada
    M1..M5    cinco ciclos fixos de autocorreção
    E1        mudança localizada, até cinco tentativas
    E2        mudança transversal, até cinco tentativas

Proteções desta versão:
- nenhuma área de trabalho, CSV ou log é apagado; uma repetição já iniciada só
  continua com --continuar;
- a pasta padrão das áreas é C:/execucoes-v2 e o orquestrador recusa C:/execucoes,
  onde estão os dados da coleta 1;
- uma invocação que falha (cota, rede, tempo) não conta como tentativa: as
  edições parciais são descartadas e a mesma invocação é refeita na retomada;
- as tentativas de E1 e E2 são contadas entre retomadas (progresso/), e o teto
  de cinco vale para a soma;
- cada linha de interacoes.csv, estados.csv e evolucoes.csv é gravada no
  momento do evento, não ao final.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from orq.agente import AgenteClaudeCode, AgenteFalso  # noqa: E402
from orq.estados import ferramentas_ausentes  # noqa: E402
from orq.estados import (CopiaDoCommit, area_limpa, commit_de, congelar,  # noqa: E402
                         dispersao, etiqueta_existe, git, medir, registrar_commit,
                         relatorio_estruturado, relatorios_estaticos,
                         restaurar_ultimo_commit, rodar_suite, verificar_invariantes)

CICLOS_CORRECAO = 5
TETO_EVOLUCAO = 5
ESTADOS = ["M0", "M1", "M2", "M3", "M4", "M5", "E1", "E2"]

# Contagens congeladas. Coleta diferente invalida a medição.
TESTES_ESPERADOS = {"base": 54, "propriedades": 1, "e1": 9, "e2": 16}
SUITES_MEDICAO = {"M": ["base", "propriedades"],
                  "E1": ["base", "propriedades", "e1"],
                  "E2": ["base", "propriedades", "e1", "e2"]}

# Sal da coleta 2: pastas e etiquetas diferentes das da coleta 1.
SAL_PASTA = "escala-v2"
SAL_ETIQUETA = "v2"
PASTA_COLETA_1 = Path("C:/execucoes")

# Limite de segurança para a linha de comando do Windows (32 767 caracteres).
LIMITE_INSTRUCAO = 30000

INSTRUCAO_M0 = (
    "Implemente integralmente o sistema descrito na especificacao em anexo. "
    "Respeite todas as restricoes tecnicas da secao 2, incluindo o esquema de "
    "banco da secao 2.1 e o ponto de entrada app/main.py com o objeto app. "
    "As oito invariantes da secao 4 devem valer apos qualquer operacao."
    "\n\n{spec}"
)
INSTRUCAO_CORRECAO = (
    "ESPECIFICACAO DO SISTEMA\n\n{spec}\n\n"
    "RELATORIOS DE ANALISE DO ESTADO ATUAL\n\n{relatorios}\n\n"
    "Corrija os problemas apontados. Nao altere o comportamento funcional "
    "descrito na especificacao."
)
# A segunda mudança chega com a primeira, que continua em vigor. Na coleta 1 a
# instrução de E2 omitia E1, e um agente removeu o campo `noturno` por julgá-lo
# fora da especificação.
BLOCO_MUDANCA_ANTERIOR = (
    "ALTERACAO ANTERIOR, JA INCORPORADA A ESPECIFICACAO E AINDA EM VIGOR\n\n"
    "{anterior}\n\n"
)
INSTRUCAO_EVOLUCAO = (
    "ESPECIFICACAO DO SISTEMA\n\n{spec}\n\n{bloco_anterior}"
    "REQUISITO DE MUDANCA\n\n{evolucao}"
)
INSTRUCAO_RETRY_EVOLUCAO = (
    "ESPECIFICACAO DO SISTEMA\n\n{spec}\n\n{bloco_anterior}"
    "REQUISITO DE MUDANCA\n\n{evolucao}\n\n"
    "RELATORIO DA TENTATIVA ANTERIOR\n\n{relatorio}\n\n"
    "Corrija as falhas apontadas sem alterar o comportamento funcional "
    "descrito na especificacao."
)

COLUNAS_INTERACOES = ["app", "repeticao", "estado", "iteracao", "tentativa",
                      "data_hora", "tipo", "segundos", "codigo_saida", "sucesso",
                      "criterio", "erro", "commit", "modelos", "custo_usd",
                      "tokens_entrada", "tokens_saida", "tokens_cache_criacao",
                      "tokens_cache_leitura", "num_turnos", "subtipo",
                      "tamanho_instrucao"]
# arquivos_tocados e linhas_*: só app/, como nas tabelas do TCC.
# *_total: o repositório inteiro, inclusive roteiros do agente fora de app/.
COLUNAS_EVOLUCOES = ["repeticao", "evolucao", "aceita", "iteracoes",
                     "arquivos_tocados", "linhas_adicionadas", "linhas_removidas",
                     "criterio_final", "commit_origem", "commit_destino",
                     "arquivos_tocados_total", "linhas_adicionadas_total",
                     "linhas_removidas_total"]
COLUNAS_ESTADOS = ["repeticao", "estado", "etiqueta", "commit_sha", "data_hora"]


class ExecucaoInterrompida(Exception):
    """Uma invocação do agente falhou; a repetição para e pode ser retomada."""


def acrescentar_linha(caminho: Path, colunas: list[str], linha: dict) -> None:
    """Acrescente uma linha ao CSV no momento do evento; nunca sobrescreve."""
    existe = caminho.exists()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "a", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas, extrasaction="ignore")
        if not existe:
            escritor.writeheader()
        escritor.writerow(linha)
        arquivo.flush()
        os.fsync(arquivo.fileno())


def ler_csv(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    with open(caminho, encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


def gravar_json(caminho: Path, dados) -> None:
    """Grave JSON de forma atômica: arquivo temporário e substituição."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporario, caminho)


class Orquestrador:
    def __init__(self, raiz: Path, agente, base_trabalho: Path, saida: Path,
                 continuar: bool):
        self.raiz = raiz
        self.agente = agente
        self.base_trabalho = base_trabalho
        self.saida = saida
        self.continuar = continuar
        self.config = raiz / "config"
        self.classificacao = json.loads(
            (raiz / "artefatos" / "classificacao.json").read_text(encoding="utf-8"))

    # ------------------------------------------------------------ nomes opacos

    @staticmethod
    def pasta_opaca(rep: int) -> str:
        """Nome de diretório que não revela o índice da repetição."""
        return hashlib.sha256(f"{SAL_PASTA}-{rep}".encode()).hexdigest()[:10]

    @staticmethod
    def rotulo_neutro(rep: int, estado: str) -> str:
        """Etiqueta Git que não revela o estágio metodológico."""
        return "s" + hashlib.sha256(f"{SAL_ETIQUETA}-{rep}-{estado}".encode()).hexdigest()[:12]

    # ------------------------------------------------------------ artefatos e caminhos

    def artefato(self, nome: str) -> str:
        return (self.raiz / "artefatos" / nome).read_text(encoding="utf-8")

    @property
    def resultados_csv(self) -> Path:
        return self.saida / "resultados.csv"

    def caminho_progresso(self, rep: int, evolucao: str) -> Path:
        return self.saida / "progresso" / f"r{rep:02d}-{evolucao}.json"

    # ------------------------------------------------------------ área de trabalho

    def preparar(self, rep: int) -> Path:
        """Crie a área da repetição; uma área existente só é reaproveitada com --continuar."""
        trabalho = self.base_trabalho / self.pasta_opaca(rep)
        if trabalho.exists():
            if not self.continuar:
                raise SystemExit(
                    f"\nERRO: a area da repeticao {rep} ja existe ({trabalho}).\n"
                    f"Nada foi apagado. Para retomar: python orquestrador.py --continuar "
                    f"--inicio {rep} --repeticoes 1\n")
            if not (trabalho / ".git").is_dir():
                raise SystemExit(f"\nERRO: {trabalho} existe, mas nao e um repositorio Git. "
                                 f"Nada foi alterado; verifique a pasta manualmente.\n")
            print(f"  retomando area de trabalho existente: {trabalho.name}")
            if not area_limpa(trabalho):
                print("  [aviso] havia edicoes nao registradas (invocacao interrompida); "
                      "descartadas, o estado volta ao ultimo commit")
                restaurar_ultimo_commit(trabalho)
            return trabalho
        trabalho.mkdir(parents=True)
        git(trabalho, "init", "-q")
        git(trabalho, "branch", "-M", "main")
        (trabalho / ".gitignore").write_text(
            "__pycache__/\n*.pyc\n*.db\n*.db-journal\n*.db-wal\n*.db-shm\n"
            ".coverage\n.coverage.*\n.pytest_cache/\n.hypothesis/\n", encoding="utf-8")
        (trabalho / "LEIA-ME.md").write_text(
            "Area de trabalho do agente. O codigo da aplicacao vive em app/.\n",
            encoding="utf-8")
        congelar(trabalho, self.rotulo_neutro(rep, "base"))
        return trabalho

    def estados_concluidos(self, rep: int, trabalho: Path) -> set[str]:
        return {estado for estado in ESTADOS
                if etiqueta_existe(trabalho, self.rotulo_neutro(rep, estado))}

    def estados_medidos(self, rep: int) -> set[str]:
        return {linha["estado"] for linha in ler_csv(self.resultados_csv)
                if linha["app"] == f"r{rep}"}

    def reparar_registros(self, rep: int, trabalho: Path, feitos: set[str]) -> None:
        """Complete registros que uma interrupção abrupta possa ter deixado de gravar.

        Uma etiqueta só existe depois de a invocação terminar com sucesso; o que
        vem depois dela (linha em estados.csv, medição, linha em evolucoes.csv)
        é reconstruído a partir da própria etiqueta e do progresso registrado.
        """
        registrados = {linha["estado"] for linha in ler_csv(self.saida / "estados.csv")
                       if str(linha["repeticao"]) == str(rep)}
        for estado in [e for e in ESTADOS if e in feitos and e not in registrados]:
            print(f"  {estado}  congelado sem linha em estados.csv; registrando pela etiqueta")
            self.registrar_estado(rep, estado,
                                  commit_de(trabalho, self.rotulo_neutro(rep, estado)))
        for estado in [e for e in ESTADOS if e in feitos and e not in self.estados_medidos(rep)]:
            print(f"  {estado}  congelado sem medicao registrada; medindo pela etiqueta")
            self.medir_estado(rep, estado, trabalho)
        evolucoes = {linha["evolucao"] for linha in ler_csv(self.saida / "evolucoes.csv")
                     if str(linha["repeticao"]) == str(rep)}
        for codigo_evolucao, anterior in (("E1", f"M{CICLOS_CORRECAO}"), ("E2", "E1")):
            if codigo_evolucao in feitos and codigo_evolucao not in evolucoes:
                print(f"  {codigo_evolucao}  congelada sem linha em evolucoes.csv; registrando")
                self.registrar_evolucao(rep, trabalho, codigo_evolucao,
                                        self.rotulo_neutro(rep, anterior))

    # ------------------------------------------------------------ registros

    def proxima_tentativa(self, rep: int, estado: str, iteracao: int) -> int:
        pasta = self.saida / "logs" / f"r{rep:02d}"
        existentes = list(pasta.glob(f"{estado}-it{iteracao:02d}-t*-prompt.txt"))
        return len(existentes) + 1

    def registrar_interacao(self, rep, estado, iteracao, tentativa, tipo, resposta,
                            instrucao, criterio="", commit="") -> None:
        meta = resposta.metadados
        acrescentar_linha(self.saida / "interacoes.csv", COLUNAS_INTERACOES, {
            "app": "app", "repeticao": rep, "estado": estado, "iteracao": iteracao,
            "tentativa": tentativa,
            "data_hora": datetime.now().isoformat(timespec="seconds"),
            "tipo": tipo, "segundos": round(resposta.segundos, 2),
            "codigo_saida": resposta.codigo_saida,
            "sucesso": "sim" if resposta.sucesso else "nao",
            "criterio": criterio, "erro": resposta.erro[:300], "commit": commit[:12],
            "modelos": meta.get("modelos", ""), "custo_usd": meta.get("custo_usd", ""),
            "tokens_entrada": meta.get("tokens_entrada", ""),
            "tokens_saida": meta.get("tokens_saida", ""),
            "tokens_cache_criacao": meta.get("tokens_cache_criacao", ""),
            "tokens_cache_leitura": meta.get("tokens_cache_leitura", ""),
            "num_turnos": meta.get("num_turnos", ""), "subtipo": meta.get("subtipo", ""),
            "tamanho_instrucao": len(instrucao),
        })

    def registrar_estado(self, rep: int, estado: str, commit: str) -> None:
        acrescentar_linha(self.saida / "estados.csv", COLUNAS_ESTADOS, {
            "repeticao": rep, "estado": estado,
            "etiqueta": self.rotulo_neutro(rep, estado), "commit_sha": commit[:12],
            "data_hora": datetime.now().isoformat(timespec="seconds")})

    # ------------------------------------------------------------ invocação

    def ajustar_tamanho(self, partes: dict, modelo: str) -> str:
        """Monte a instrução e, se exceder o limite, encurte só os relatórios."""
        instrucao = modelo.format(**partes)
        excesso = len(subprocess.list2cmdline([instrucao])) - LIMITE_INSTRUCAO
        for chave in ("relatorios", "relatorio"):
            if excesso > 0 and chave in partes:
                aviso = "\n[relatorio encurtado por limite de tamanho]"
                partes = dict(partes, **{chave: partes[chave][:max(0, len(partes[chave])
                                                                   - excesso - len(aviso) - 50)]
                                          + aviso})
                instrucao = modelo.format(**partes)
                excesso = len(subprocess.list2cmdline([instrucao])) - LIMITE_INSTRUCAO
        if excesso > 0:
            raise RuntimeError("instrucao acima do limite mesmo sem relatorios")
        return instrucao

    def invocar(self, rep: int, trabalho: Path, estado: str, iteracao: int,
                instrucao: str, tipo: str):
        """Invoque o agente, arquive prompt e resposta e trate a falha.

        Em caso de falha, as edições parciais são descartadas e a repetição é
        interrompida; a mesma invocação será refeita na retomada.
        """
        tentativa = self.proxima_tentativa(rep, estado, iteracao)
        pasta_logs = self.saida / "logs" / f"r{rep:02d}"
        pasta_logs.mkdir(parents=True, exist_ok=True)
        prefixo = f"{estado}-it{iteracao:02d}-t{tentativa}"
        (pasta_logs / f"{prefixo}-prompt.txt").write_text(instrucao, encoding="utf-8")
        resposta = self.agente.executar(instrucao, trabalho)
        (pasta_logs / f"{prefixo}-resposta.txt").write_text(resposta.texto or "",
                                                             encoding="utf-8")
        if resposta.bruto:
            (pasta_logs / f"{prefixo}-resposta-bruta.json").write_text(
                resposta.bruto, encoding="utf-8")
        if not resposta.sucesso:
            restaurar_ultimo_commit(trabalho)
            self.registrar_interacao(rep, estado, iteracao, tentativa, tipo, resposta,
                                     instrucao, criterio="falha da invocacao")
            motivo = "limite de uso do plano" if resposta.cota_esgotada else "falha do agente"
            raise ExecucaoInterrompida(
                f"r{rep} {estado} iteracao {iteracao}: {motivo} "
                f"(codigo {resposta.codigo_saida}): {resposta.erro[:200]}")
        return resposta, tentativa

    # ------------------------------------------------------------ instrumentos

    def medir_estado(self, rep: int, estado: str, trabalho: Path) -> dict:
        grupo = "M" if estado.startswith("M") else estado
        suites = SUITES_MEDICAO[grupo]
        esperado = sum(TESTES_ESPERADOS[nome] for nome in suites)
        with CopiaDoCommit(trabalho, self.rotulo_neutro(rep, estado)) as copia:
            return medir(self.raiz, f"r{rep}", estado, copia.codigo, copia.banco,
                         self.resultados_csv, suites, esperado)

    def feedback_do_ciclo(self, trabalho: Path, ciclo: int) -> str:
        """Relatórios do estado atual (o último congelado) para o ciclo de correção."""
        suites = SUITES_MEDICAO["M"]
        esperado = sum(TESTES_ESPERADOS[nome] for nome in suites)
        with CopiaDoCommit(trabalho, "HEAD") as copia:
            base = rodar_suite(self.raiz, copia.codigo, suites,
                               copia.pasta / "ciclo.xml", copia.banco, esperado)
            inv = verificar_invariantes(self.raiz, copia.banco)
            estaticos = relatorios_estaticos(copia.codigo, self.config)
        return estaticos + "\n\n" + relatorio_estruturado(None, base, set(), inv, ciclo)

    def muda_acumulado(self, evolucao: str) -> set[str]:
        acumulado: set[str] = set()
        for anterior in ("E1", "E2"):
            acumulado |= {nome for nome, classe in self.classificacao.get(anterior, {}).items()
                          if classe == "MUDA"}
            if anterior == evolucao:
                break
        return acumulado

    def avaliar_evolucao(self, trabalho: Path, codigo_evolucao: str, commit: str,
                         iteracao: int) -> tuple[bool, str, str]:
        """Aplique o critério de aceitação ao commit da tentativa."""
        suite_nova = codigo_evolucao.lower()
        regressao = SUITES_MEDICAO[codigo_evolucao][:-1]
        esperado_novo = TESTES_ESPERADOS[suite_nova]
        esperado_base = sum(TESTES_ESPERADOS[nome] for nome in regressao)
        muda = self.muda_acumulado(codigo_evolucao)
        with CopiaDoCommit(trabalho, commit) as copia:
            novo = rodar_suite(self.raiz, copia.codigo, [suite_nova],
                               copia.pasta / "aceitacao.xml", copia.banco, esperado_novo)
            base = rodar_suite(self.raiz, copia.codigo, regressao,
                               copia.pasta / "regressao.xml", copia.banco, esperado_base)
            inv = verificar_invariantes(self.raiz, copia.banco)

        def sufixo(nome: str) -> str:
            return nome.split("::")[0].split(".")[-1] + "::" + nome.split("::")[-1]
        muda_norm = {sufixo(nome) for nome in muda}
        falhas_base = {nome for nome in base["reprovados"] if sufixo(nome) not in muda_norm}
        aplicacao_importa = novo["importa"] and base["importa"]
        coleta_ok = novo["valida"] and base["valida"] and inv.get("avaliavel", False)
        aceito = (coleta_ok and not novo["reprovados"] and not falhas_base
                  and not inv.get("violadas"))
        if aceito:
            criterio = "aceito: suite nova 100%, comportamento existente 100%, invariantes ok"
        elif not aplicacao_importa:
            criterio = "pendente: a aplicacao nao importa"
        elif not coleta_ok:
            criterio = (f"INSTRUMENTO INVALIDO: nova={novo['coletados']}/{esperado_novo}, "
                        f"base={base['coletados']}/{esperado_base}, "
                        f"invariantes avaliaveis={inv.get('avaliavel')}")
        else:
            criterio = (f"pendente: {len(novo['reprovados'])} falhas novas, "
                        f"{len(falhas_base)} reprovados no comportamento existente, "
                        f"inv={inv.get('violadas')}")
        relatorio = relatorio_estruturado(novo, base, muda, inv, iteracao)
        return aceito, criterio, relatorio

    # ------------------------------------------------------------ execução

    def executar(self, rep: int) -> None:
        print(f"\n=== repeticao {rep} ===")
        trabalho = self.preparar(rep)
        feitos = self.estados_concluidos(rep, trabalho)
        if feitos:
            print(f"  ja congelados: {' '.join(e for e in ESTADOS if e in feitos)}")
            self.reparar_registros(rep, trabalho, feitos)

        spec = self.artefato("spec.md")
        if "M0" not in feitos:
            instrucao = self.ajustar_tamanho({"spec": spec}, INSTRUCAO_M0)
            resposta, tentativa = self.invocar(rep, trabalho, "M0", 1, instrucao, "geracao")
            commit = congelar(trabalho, self.rotulo_neutro(rep, "M0"))
            self.registrar_estado(rep, "M0", commit)
            self.registrar_interacao(rep, "M0", 1, tentativa, "geracao", resposta,
                                     instrucao, commit=commit)
            m = self.medir_estado(rep, "M0", trabalho)
            print(f"  M0  pylint={m.get('pylint_total', '?')} "
                  f"testes={m.get('testes_passaram', '?')}/{m.get('testes_total', '?')} "
                  f"importa={m.get('app_importa', '?')}")

        for ciclo in range(1, CICLOS_CORRECAO + 1):
            estado = f"M{ciclo}"
            if estado in feitos:
                continue
            relatorios = self.feedback_do_ciclo(trabalho, ciclo)
            instrucao = self.ajustar_tamanho({"spec": spec, "relatorios": relatorios},
                                             INSTRUCAO_CORRECAO)
            resposta, tentativa = self.invocar(rep, trabalho, estado, ciclo, instrucao,
                                               "correcao")
            commit = congelar(trabalho, self.rotulo_neutro(rep, estado))
            self.registrar_estado(rep, estado, commit)
            self.registrar_interacao(rep, estado, ciclo, tentativa, "correcao", resposta,
                                     instrucao, criterio=f"ciclo fixo {ciclo}/{CICLOS_CORRECAO}",
                                     commit=commit)
            m = self.medir_estado(rep, estado, trabalho)
            print(f"  {estado}  pylint={m.get('pylint_total', '?')} "
                  f"testes={m.get('testes_passaram', '?')}/{m.get('testes_total', '?')}")

        anterior = self.rotulo_neutro(rep, f"M{CICLOS_CORRECAO}")
        for codigo_evolucao, arquivo in (("E1", "evolucao-e1.md"), ("E2", "evolucao-e2.md")):
            if codigo_evolucao in feitos:
                anterior = self.rotulo_neutro(rep, codigo_evolucao)
                continue
            self.executar_evolucao(rep, trabalho, codigo_evolucao, arquivo, anterior, spec)
            anterior = self.rotulo_neutro(rep, codigo_evolucao)

    def executar_evolucao(self, rep: int, trabalho: Path, codigo_evolucao: str,
                          arquivo: str, anterior: str, spec: str) -> None:
        texto = self.artefato(arquivo)
        bloco_anterior = (BLOCO_MUDANCA_ANTERIOR.format(anterior=self.artefato("evolucao-e1.md"))
                          if codigo_evolucao == "E2" else "")
        caminho = self.caminho_progresso(rep, codigo_evolucao)
        progresso = (json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists()
                     else {"origem": commit_de(trabalho, anterior), "iteracoes": []})
        iteracoes = progresso["iteracoes"]
        esperado_head = iteracoes[-1]["commit"] if iteracoes else progresso["origem"]
        if (commit_de(trabalho, "HEAD") != esperado_head
                and commit_de(trabalho, "HEAD~1") == esperado_head):
            # Interrupção entre o commit da tentativa e o registro do progresso:
            # a tentativa não chegou a ser registrada nem avaliada. Ela é tratada
            # como invocação que falhou: o commit sai do ramo e a tentativa é refeita.
            print(f"  [aviso] {codigo_evolucao}: tentativa nao registrada descartada "
                  f"(commit {commit_de(trabalho, 'HEAD')[:12]}); sera refeita")
            git(trabalho, "reset", "-q", "--hard", esperado_head)
        if commit_de(trabalho, "HEAD") != esperado_head:
            raise SystemExit(
                f"\nERRO: r{rep} {codigo_evolucao}: o ultimo commit da area nao corresponde "
                f"ao progresso registrado ({caminho}). Nada foi alterado. Registre a "
                f"ocorrencia e me envie a pasta progresso/ antes de continuar.\n")
        if iteracoes:
            print(f"  {codigo_evolucao}  retomando: {len(iteracoes)} tentativa(s) ja feita(s)")
        if iteracoes and not iteracoes[-1]["avaliado"]:
            # A tentativa terminou e foi registrada, mas a avaliação não chegou
            # ao fim. Ela é refeita sobre o mesmo commit, sem nova invocação.
            self.concluir_tentativa(rep, trabalho, codigo_evolucao, caminho, progresso)

        aceito = bool(iteracoes) and iteracoes[-1]["aceito"]
        while not aceito and len(iteracoes) < TETO_EVOLUCAO:
            iteracao = len(iteracoes) + 1
            partes = {"spec": spec, "bloco_anterior": bloco_anterior, "evolucao": texto}
            if iteracoes:
                partes["relatorio"] = iteracoes[-1]["relatorio"]
                instrucao = self.ajustar_tamanho(partes, INSTRUCAO_RETRY_EVOLUCAO)
            else:
                instrucao = self.ajustar_tamanho(partes, INSTRUCAO_EVOLUCAO)
            tipo = f"evolucao-{codigo_evolucao.lower()}"
            resposta, tentativa = self.invocar(rep, trabalho, codigo_evolucao, iteracao,
                                               instrucao, tipo)
            commit = registrar_commit(trabalho)
            meta = resposta.metadados
            iteracoes.append({
                "iteracao": iteracao, "commit": commit, "avaliado": False,
                "aceito": False, "criterio": "", "relatorio": "",
                "interacao": {
                    "tentativa": tentativa, "tipo": tipo, "segundos": round(resposta.segundos, 2),
                    "codigo_saida": resposta.codigo_saida, "erro": resposta.erro[:300],
                    "tamanho_instrucao": len(instrucao),
                    **{chave: meta.get(chave, "") for chave in (
                        "modelos", "custo_usd", "tokens_entrada", "tokens_saida",
                        "tokens_cache_criacao", "tokens_cache_leitura", "num_turnos",
                        "subtipo")}}})
            gravar_json(caminho, progresso)
            self.concluir_tentativa(rep, trabalho, codigo_evolucao, caminho, progresso)
            aceito = iteracoes[-1]["aceito"]

        etiqueta = self.rotulo_neutro(rep, codigo_evolucao)
        commit = congelar(trabalho, etiqueta)
        self.registrar_estado(rep, codigo_evolucao, commit)
        self.medir_estado(rep, codigo_evolucao, trabalho)
        self.registrar_evolucao(rep, trabalho, codigo_evolucao, anterior)

    def concluir_tentativa(self, rep: int, trabalho: Path, codigo_evolucao: str,
                           caminho: Path, progresso: dict) -> None:
        """Avalie a última tentativa registrada e grave o resultado."""
        registro = progresso["iteracoes"][-1]
        aceito, criterio, relatorio = self.avaliar_evolucao(
            trabalho, codigo_evolucao, registro["commit"], registro["iteracao"])
        registro.update({"avaliado": True, "aceito": aceito, "criterio": criterio,
                         "relatorio": relatorio})
        gravar_json(caminho, progresso)
        dados = registro["interacao"]
        acrescentar_linha(self.saida / "interacoes.csv", COLUNAS_INTERACOES, {
            "app": "app", "repeticao": rep, "estado": codigo_evolucao,
            "iteracao": registro["iteracao"],
            "data_hora": datetime.now().isoformat(timespec="seconds"),
            "sucesso": "sim", "criterio": criterio, "commit": registro["commit"][:12],
            **dados})
        print(f"  {codigo_evolucao}  tentativa {registro['iteracao']}: {criterio}")

    def registrar_evolucao(self, rep: int, trabalho: Path, codigo_evolucao: str,
                           anterior: str) -> None:
        """Grave a linha de evolucoes.csv a partir das etiquetas e do progresso."""
        etiqueta = self.rotulo_neutro(rep, codigo_evolucao)
        caminho = self.caminho_progresso(rep, codigo_evolucao)
        iteracoes = (json.loads(caminho.read_text(encoding="utf-8"))["iteracoes"]
                     if caminho.exists() else [])
        aceito = bool(iteracoes) and iteracoes[-1].get("aceito", False)
        disp = dispersao(trabalho, anterior, etiqueta, "app")
        total = dispersao(trabalho, anterior, etiqueta)
        acrescentar_linha(self.saida / "evolucoes.csv", COLUNAS_EVOLUCOES, {
            "repeticao": rep, "evolucao": codigo_evolucao,
            "aceita": "sim" if aceito else "nao", "iteracoes": len(iteracoes),
            **disp, "criterio_final": iteracoes[-1].get("criterio", "") if iteracoes else "",
            "commit_origem": commit_de(trabalho, anterior)[:12],
            "commit_destino": commit_de(trabalho, etiqueta)[:12],
            **{f"{chave}_total": valor for chave, valor in total.items()}})
        print(f"  {codigo_evolucao}  tentativas={len(iteracoes)} "
              f"arquivos={disp['arquivos_tocados']} "
              f"linhas=+{disp['linhas_adicionadas']}/-{disp['linhas_removidas']} -> "
              f"{'aceita' if aceito else 'nao aceita'}")


# ---------------------------------------------------------------- verificações

def verificar_ambiente(raiz: Path, base_trabalho: Path, simulado: bool) -> None:
    problemas = []
    for chave in ("user.name", "user.email"):
        processo = subprocess.run(["git", "config", "--global", chave],
                                  capture_output=True, text=True)
        if not processo.stdout.strip():
            problemas.append(f"git config --global {chave} nao definido")
    ausentes = ferramentas_ausentes()
    if ausentes:
        problemas.append("ferramentas nao encontradas neste Python (" + ", ".join(ausentes)
                         + "): ative a venv com Activate.ps1 e rode de novo")
    for exigido in ("medir.py", "artefatos", "oracle", "config", "pytest.ini"):
        if not (raiz / exigido).exists():
            problemas.append(f"{exigido} nao encontrado em {raiz}")
    if raiz in base_trabalho.parents or base_trabalho == raiz or base_trabalho in raiz.parents:
        problemas.append("a pasta de trabalho do agente nao pode ficar dentro da pesquisa "
                         "nem conte-la")
    try:
        if base_trabalho.resolve() == PASTA_COLETA_1.resolve():
            problemas.append("C:/execucoes guarda a coleta 1 e nao pode ser usada")
    except OSError:
        pass
    if not simulado:
        manifesto = raiz / "manifesto-experimento.json"
        if not manifesto.exists():
            problemas.append("manifesto-experimento.json ausente: rode manifesto.py "
                             "depois de --verificar-agente e antes da coleta")
        else:
            registrado = json.loads(manifesto.read_text(encoding="utf-8"))
            versao_registrada = registrado.get("agente", {}).get("claude_code", "")
            versao_atual = AgenteClaudeCode().versao()
            if versao_registrada and versao_atual != versao_registrada:
                problemas.append(f"versao do Claude Code mudou: manifesto "
                                 f"'{versao_registrada}', agora '{versao_atual}'")
            for nome, registrada in (registrado.get("ferramentas") or {}).items():
                try:
                    atual = metadata.version(nome)
                except metadata.PackageNotFoundError:
                    atual = "nao instalado"
                if registrada != atual:
                    problemas.append(f"versao de {nome} mudou: manifesto '{registrada}', "
                                     f"agora '{atual}'")
    if problemas:
        print("\nERRO DE AMBIENTE: nada foi executado:\n")
        for problema in problemas:
            print(f"  - {problema}")
        sys.exit(1)


TRAVAS: list = []


def travar_saida(saida: Path):
    """Impeça dois orquestradores simultâneos sobre a mesma pasta de saída.

    A trava é do sistema operacional e some quando o processo termina, mesmo
    que ele seja fechado à força; não há arquivo de trava "velho" a apagar.
    """
    arquivo = open(saida / ".orquestrador.trava", "a+", encoding="utf-8")  # pylint: disable=consider-using-with
    try:
        if os.name == "nt":
            import msvcrt  # pylint: disable=import-outside-toplevel,import-error
            arquivo.seek(0)
            msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # pylint: disable=import-outside-toplevel,import-error
            fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        arquivo.close()
        sys.exit("\nERRO: outro orquestrador esta rodando com esta mesma pasta "
                 "(outra janela do PowerShell?).\nNada foi executado. Feche a outra "
                 "execucao ou espere ela terminar.\nSe tiver certeza de que nao ha outra "
                 "execucao, rode o mesmo comando acrescentando --sem-trava.\n")
    return arquivo


def verificar_agente() -> None:
    """Faça uma chamada mínima ao agente e mostre o que será registrado.

    Gasta uma fração pequena da cota. Roda numa pasta temporária, longe da
    pesquisa e das áreas de trabalho.
    """
    agente = AgenteClaudeCode()
    print(f"Claude Code: {agente.versao()}")
    with tempfile.TemporaryDirectory(prefix="tcc_v2_verificacao_") as pasta:
        resposta = agente.executar("Responda apenas com a palavra OK.", Path(pasta))
    print(f"codigo de saida: {resposta.codigo_saida}  sucesso: {resposta.sucesso}")
    print(f"texto: {resposta.texto.strip()[:200]!r}")
    for chave, valor in resposta.metadados.items():
        print(f"  {chave}: {valor}")
    if resposta.metadados.get("formato") != "json":
        print("\nATENCAO: a saida nao veio em JSON. Os campos de modelo e tokens ficarao vazios.")
    if not resposta.sucesso:
        print(f"\nFALHA: {resposta.erro[:500]}")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--trabalho", default=None,
                    help="pasta das areas do agente (padrao: C:/execucoes-v2)")
    ap.add_argument("--repeticoes", type=int, default=1)
    ap.add_argument("--inicio", type=int, default=1)
    ap.add_argument("--continuar", action="store_true",
                    help="retoma a repeticao a partir dos estados ja congelados")
    ap.add_argument("--simulado", action="store_true",
                    help="agente falso; tudo vai para simulacao/ e para uma pasta temporaria")
    ap.add_argument("--saida", default=None,
                    help="pasta dos CSV e logs (padrao: coleta/, ou simulacao/<data-hora>/)")
    ap.add_argument("--verificar-agente", action="store_true")
    ap.add_argument("--sem-trava", action="store_true",
                    help="dispensa a trava contra duas execucoes simultaneas")
    args = ap.parse_args()

    if args.verificar_agente:
        verificar_agente()
        return

    raiz = Path(args.raiz).resolve()
    if args.simulado:
        marca = datetime.now().strftime("%Y%m%d-%H%M%S")
        saida = Path(args.saida).resolve() if args.saida else raiz / "simulacao" / marca
        base_trabalho = (Path(args.trabalho).resolve() if args.trabalho
                         else Path(tempfile.mkdtemp(prefix="tcc_v2_simulacao_")))
        if not args.saida and args.continuar:
            sys.exit("Para retomar uma simulacao, informe --saida e --trabalho da simulacao.")
    else:
        saida = Path(args.saida).resolve() if args.saida else raiz / "coleta"
        padrao = Path("C:/execucoes-v2") if os.name == "nt" else Path.home() / "execucoes-v2"
        base_trabalho = Path(args.trabalho).resolve() if args.trabalho else padrao
    verificar_ambiente(raiz, base_trabalho, args.simulado)
    base_trabalho.mkdir(parents=True, exist_ok=True)
    saida.mkdir(parents=True, exist_ok=True)
    if not args.sem_trava:
        TRAVAS.append(travar_saida(saida))  # mantida aberta até o fim do processo

    agente = AgenteFalso() if args.simulado else AgenteClaudeCode()
    print("MODO SIMULADO: nenhuma chamada ao agente real" if args.simulado
          else f"Agente: {agente.nome} versao {agente.versao()}")
    print(f"Pesquisa: {raiz}\nSaidas: {saida}\nAreas do agente: {base_trabalho}")

    orq = Orquestrador(raiz, agente, base_trabalho, saida, args.continuar)
    atual = args.inicio
    ultima = args.inicio + args.repeticoes - 1
    try:
        for atual in range(args.inicio, ultima + 1):
            orq.executar(atual)
        print(f"\nRepeticoes {args.inicio} a {ultima} concluidas.")
    except ExecucaoInterrompida as erro:
        restantes = ultima - atual + 1
        print("\n" + "=" * 64)
        print("EXECUCAO INTERROMPIDA - nada foi perdido")
        print(f"  Motivo: {erro}")
        print(f"  Repeticao em andamento: {atual}")
        print("  As edicoes parciais da invocacao que falhou foram descartadas.")
        print("  Quando a cota renovar, retome EXATAMENTE com:")
        print(f"    python orquestrador.py --continuar --inicio {atual} --repeticoes {restantes}")
        print("=" * 64 + "\n")
        sys.exit(2)
    except KeyboardInterrupt:
        print(f"\nInterrompido pelo usuario na repeticao {atual}. Para retomar:\n"
              f"  python orquestrador.py --continuar --inicio {atual} "
              f"--repeticoes {ultima - atual + 1}\n")
        sys.exit(130)


if __name__ == "__main__":
    main()
