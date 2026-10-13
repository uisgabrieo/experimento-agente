"""Coleta os indicadores empregados na avaliação experimental (instrumento v2).

Uso:
    python medir.py --app r1 --estado M0 --codigo <pasta> --saida resultados.csv \
        --testes <raiz>/oracle/base <raiz>/oracle/propriedades \
        --extra-path <raiz> --db <arquivo.db> --esperado 55

O script executa Pylint, Radon, Bandit, cobertura, pytest e o oráculo de
invariantes sobre o código de uma aplicação. Os resultados são acrescentados a
`--saida` e detalhados em `detalhes/`, ao lado dela. As regressões surgem da
comparação com o estado imediatamente anterior da mesma aplicação.

Diferenças em relação à versão 1, todas declaradas na metodologia:

- a configuração das ferramentas é do instrumento (`config/`); arquivos de
  configuração deixados na pasta avaliada (`.pylintrc`, `.bandit`,
  `setup.cfg`, `pyproject.toml`, `.coveragerc`) não alteram a medição;
- as supressões inline são contadas (`# pylint: disable`, `# nosec`,
  `# pragma: no cover`), além das ocorrências que continuam visíveis;
- o Bandit analisa apenas `app/`, como Pylint e Radon;
- a coleta do pytest é válida só com o número exato de testes (`--esperado`);
- uma aplicação que não importa é registrada como resultado (`app_importa`),
  não como falha de instrumento.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ORDEM_ESTADOS = ["M0", "M1", "M2", "M3", "M4", "M5", "E1", "E2"]
CONFIG_PADRAO = Path(__file__).resolve().parent / "config"

COLUNAS = [
    "app", "estado", "data_hora",
    "arquivos_py", "linhas_codigo",
    "pylint_convention", "pylint_refactor", "pylint_warning", "pylint_error",
    "pylint_total", "pylint_nota",
    "cc_media", "cc_maxima", "funcoes_cc_acima_10", "total_funcoes",
    "mi_medio", "mi_minimo",
    "bandit_alta", "bandit_media", "bandit_baixa", "bandit_total",
    "testes_total", "testes_passaram", "testes_falharam",
    "taxa_aprovacao_pct", "cobertura_pct",
    "regressoes", "regressoes_reais", "falhas_legitimas", "testes_regredidos",
    "inv_avaliavel", "inv1", "inv2", "inv3", "inv4", "inv5", "inv6",
    "inv7", "inv8", "invariantes_violadas",
    "instrumentos_validos", "ferramentas_com_falha",
    # Colunas acrescentadas na versão 2.
    "testes_esperados", "app_importa",
    "pylint_supressoes", "pylint_config_agente",
    "bandit_nosec", "cobertura_pragmas",
]

# Arquivos de configuração que as ferramentas procurariam na pasta avaliada.
CONFIGURACOES_DE_FERRAMENTAS = (".pylintrc", "pylintrc", "pyproject.toml",
                                "setup.cfg", "tox.ini", ".bandit", "radon.cfg",
                                ".coveragerc")


def ambiente_base() -> dict:
    """Ambiente dos subprocessos: UTF-8 e sem variáveis que mudem as ferramentas."""
    ambiente = dict(os.environ)
    for variavel in ("PYLINTRC", "RADONCFG", "COVERAGE_RCFILE",
                     "CHAVE_COORDENADOR", "CHAVE_PROFISSIONAL",
                     "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        ambiente.pop(variavel, None)
    ambiente["PYTHONUTF8"] = "1"
    ambiente["PYTHONIOENCODING"] = "utf-8"
    return ambiente


def rodar(cmd, cwd, env=None, timeout=600):
    """Execute um comando e devolva (stdout, stderr, código de término)."""
    try:
        processo = subprocess.run(
            cmd, cwd=cwd, env=env or ambiente_base(), capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return processo.stdout, processo.stderr, processo.returncode
    except subprocess.TimeoutExpired:
        print(f"  [aviso] tempo limite ({timeout}s) em {' '.join(map(str, cmd[1:3]))[:60]}",
              file=sys.stderr)
        return "", f"tempo limite de {timeout}s excedido", -2
    except Exception as erro:  # pylint: disable=broad-except
        print(f"  [aviso] falha ao rodar {' '.join(map(str, cmd[1:3]))[:60]}: {erro}",
              file=sys.stderr)
        return "", str(erro), -1


def alvos_python(codigo: Path):
    """Liste os arquivos que fazem parte da análise estática.

    A unidade observada é o pacote `app/` da aplicação gerada, o mesmo que
    compõe o relatório devolvido ao agente.
    """
    ignorar = {".venv", "venv", "__pycache__", ".git", "tests", "test",
               ".pytest_cache"}
    pacote = codigo / "app"
    raiz_busca = pacote if pacote.is_dir() else codigo
    arquivos = []
    for caminho_arquivo in sorted(raiz_busca.rglob("*.py")):
        if any(parte in ignorar for parte in caminho_arquivo.relative_to(codigo).parts):
            continue
        arquivos.append(caminho_arquivo)
    return arquivos


def contar_linhas(arquivos):
    total = 0
    for arquivo in arquivos:
        try:
            with open(arquivo, encoding="utf-8", errors="ignore") as arquivo_aberto:
                for linha in arquivo_aberto:
                    if linha.strip() and not linha.strip().startswith("#"):
                        total += 1
        except OSError:
            pass
    return total


def contar_padrao(arquivos, padrao: str) -> int:
    """Conte as linhas que contêm o padrão (expressão regular)."""
    regex = re.compile(padrao)
    total = 0
    for arquivo in arquivos:
        try:
            texto = arquivo.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        total += sum(1 for linha in texto.splitlines() if regex.search(linha))
    return total


def configuracoes_do_agente(codigo: Path) -> str:
    """Liste arquivos de configuração de ferramentas presentes na pasta avaliada.

    Eles não afetam a medição v2, mas sua presença é registrada: na coleta 1,
    uma repetição criou `.pylintrc` desativando mensagens que o relatório
    apontava.
    """
    encontrados = []
    for nome in CONFIGURACOES_DE_FERRAMENTAS:
        for caminho in [codigo / nome, codigo / "app" / nome]:
            if caminho.is_file():
                encontrados.append(str(caminho.relative_to(codigo)).replace("\\", "/"))
    return "; ".join(sorted(set(encontrados)))


def medir_pylint(codigo, arquivos, config: Path):
    """Reúna ocorrências, supressões e nota do Pylint, com configuração fixa.

    `--rcfile` impede que um `.pylintrc` ou `pyproject.toml` deixado na pasta
    avaliada mude o que é medido. As supressões inline continuam valendo, como
    no relatório entregue ao agente, mas cada ocorrência suprimida é contada
    pela mensagem informativa `suppressed-message` (I0020).
    """
    resultado = {"convention": 0, "refactor": 0, "warning": 0, "error": 0,
                 "total": 0, "nota": "", "supressoes": 0, "por_simbolo": {},
                 "suprimidas_por_simbolo": {}, "valido": False}
    if not arquivos:
        return resultado
    rel = [str(arquivo.relative_to(codigo)) for arquivo in arquivos]
    saida, erro, _ = rodar([sys.executable, "-m", "pylint",
                            f"--rcfile={config / 'pylintrc'}", "--persistent=n",
                            "--output-format=json2",
                            "--enable=suppressed-message", *rel], codigo)
    try:
        dados = json.loads(saida)
        mensagens = dados["messages"]
        nota = dados["statistics"]["score"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"  [ERRO] Pylint nao produziu JSON interpretavel: {erro[-300:]}",
              file=sys.stderr)
        return resultado
    resultado["valido"] = True
    resultado["nota"] = f"{nota:.2f}" if isinstance(nota, (int, float)) else ""
    for mensagem in mensagens:
        tipo = mensagem.get("type", "")
        simbolo = mensagem.get("symbol", "")
        if simbolo == "suppressed-message":
            resultado["supressoes"] += 1
            alvo = re.search(r"Suppressed '([^']+)'", mensagem.get("message", ""))
            nome = alvo.group(1) if alvo else "?"
            resultado["suprimidas_por_simbolo"][nome] = (
                resultado["suprimidas_por_simbolo"].get(nome, 0) + 1)
            continue
        if tipo == "fatal":
            tipo = "error"
        if tipo in ("convention", "refactor", "warning", "error"):
            resultado[tipo] += 1
            resultado["por_simbolo"][simbolo] = resultado["por_simbolo"].get(simbolo, 0) + 1
    resultado["total"] = (resultado["convention"] + resultado["refactor"]
                          + resultado["warning"] + resultado["error"])
    return resultado


def medir_radon(arquivos, neutra: Path):
    """Reúna a complexidade ciclomática e o índice de manutenibilidade.

    O Radon lê `radon.cfg`, `setup.cfg` e `pyproject.toml` da pasta corrente.
    Por isso ele roda numa pasta vazia, com caminhos absolutos.
    """
    resultado = {"cc_media": 0.0, "cc_maxima": 0, "acima_10": 0, "total_funcoes": 0,
                 "mi_medio": 0.0, "mi_minimo": 0.0, "valido": False}
    if not arquivos:
        return resultado
    caminhos = [str(arquivo.resolve()) for arquivo in arquivos]
    ambiente = ambiente_base()
    ambiente["HOME"] = str(neutra)
    ambiente["USERPROFILE"] = str(neutra)

    saida, _, _ = rodar([sys.executable, "-m", "radon", "cc", "-j", *caminhos],
                        neutra, env=ambiente)
    try:
        dados = json.loads(saida) if saida.strip() else {}
    except json.JSONDecodeError:
        dados = {}
    complexidades = []
    for blocos in dados.values():
        if not isinstance(blocos, list):
            continue
        for bloco in blocos:
            complexidade = bloco.get("complexity")
            if isinstance(complexidade, int):
                complexidades.append(complexidade)
    if complexidades:
        resultado["cc_media"] = round(sum(complexidades) / len(complexidades), 2)
        resultado["cc_maxima"] = max(complexidades)
        resultado["acima_10"] = sum(1 for valor in complexidades if valor > 10)
        resultado["total_funcoes"] = len(complexidades)

    saida, _, _ = rodar([sys.executable, "-m", "radon", "mi", "-j", *caminhos],
                        neutra, env=ambiente)
    try:
        dados = json.loads(saida) if saida.strip() else {}
        resultado["valido"] = True
    except json.JSONDecodeError:
        dados = {}
        print("  [ERRO] Radon nao produziu JSON interpretavel", file=sys.stderr)
    valores = [dado["mi"] for dado in dados.values()
               if isinstance(dado, dict) and "mi" in dado]
    if valores:
        resultado["mi_medio"] = round(sum(valores) / len(valores), 2)
        resultado["mi_minimo"] = round(min(valores), 2)
    return resultado


def medir_bandit(arquivos, config: Path, neutra: Path):
    """Conte os achados do Bandit, por gravidade, e as supressões `# nosec`.

    Analisa os mesmos arquivos de `app/` que Pylint e Radon; a versão 1
    varria a raiz da pasta avaliada. `--ini` aponta para o arquivo do
    instrumento: sem ele, o Bandit procuraria um `.bandit` na pasta analisada.
    """
    resultado = {"alta": 0, "media": 0, "baixa": 0, "total": 0, "nosec": 0,
                 "valido": False}
    if not arquivos:
        resultado["valido"] = True
        return resultado
    saida, erro, _ = rodar([sys.executable, "-m", "bandit", "-f", "json", "-q",
                            "--ini", str(config / "bandit.ini"),
                            *[str(arquivo.resolve()) for arquivo in arquivos]], neutra)
    try:
        inicio = saida.find("{")
        dados = json.loads(saida[inicio:]) if inicio >= 0 else None
        if not isinstance(dados, dict):
            raise json.JSONDecodeError("sem JSON", saida, 0)
        resultado["valido"] = True
    except json.JSONDecodeError:
        print(f"  [ERRO] Bandit nao produziu JSON interpretavel: {erro[-300:]}",
              file=sys.stderr)
        return resultado
    mapa = {"HIGH": "alta", "MEDIUM": "media", "LOW": "baixa"}
    for achado in dados.get("results", []):
        chave = mapa.get(achado.get("issue_severity", ""))
        if chave:
            resultado[chave] += 1
    resultado["total"] = resultado["alta"] + resultado["media"] + resultado["baixa"]
    resultado["nosec"] = int(dados.get("metrics", {}).get("_totals", {}).get("nosec", 0))
    return resultado


def ambiente_da_suite(codigo, extra_path, banco):
    """PYTHONPATH com a pasta avaliada e a raiz do oráculo, e o banco da medição."""
    ambiente = ambiente_base()
    caminhos = [str(codigo)]
    if extra_path:
        caminhos.append(str(extra_path))
    ambiente["PYTHONPATH"] = os.pathsep.join(caminhos)
    if banco:
        ambiente["DATABASE_URL"] = f"sqlite:///{banco}"
        ambiente["SUITE_TCC"] = "1"
    return ambiente


def opcoes_pytest(extra_path):
    """Opções comuns às duas execuções da suíte (cobertura e canônica).

    A configuração do pytest vem da raiz do instrumento. Arquivos `pytest.ini`,
    `conftest.py` ou `pyproject.toml` deixados na pasta avaliada não participam.
    """
    opcoes = ["-q", "-p", "no:cacheprovider"]
    if extra_path:
        raiz = Path(extra_path).resolve()
        if (raiz / "pytest.ini").is_file():
            opcoes += ["-c", str(raiz / "pytest.ini")]
        opcoes += [f"--rootdir={raiz}"]
    return opcoes


def verificar_importacao(codigo, extra_path, banco):
    """Tente importar `app.main`, como faz a suíte.

    Devolve (importa, erro, travou). `travou` indica que a importação não
    terminou no tempo limite, como aconteceria com um servidor iniciado na
    importação; nesse caso a suíte também travaria e não é executada.
    """
    ambiente = ambiente_da_suite(codigo, extra_path, banco)
    _, erro, codigo_saida = rodar([sys.executable, "-c", "import app.main"],
                                  codigo, env=ambiente, timeout=300)
    if codigo_saida == 0:
        return True, "", False
    linhas = [linha for linha in erro.strip().splitlines() if linha.strip()]
    return False, (linhas[-1] if linhas else f"codigo {codigo_saida}")[:300], codigo_saida == -2


def medir_pytest(codigo, saida_xml: Path, testes=None, extra_path=None, banco=None):
    """Execute a suíte indicada e consolide os resultados emitidos pelo pytest."""
    resultado = {"total": 0, "passaram": 0, "falharam": 0,
                 "aprovados": set(), "reprovados": set(), "falhas": {}, "saida": ""}
    if saida_xml.exists():
        saida_xml.unlink()
    alvos = list(testes) if testes else []
    saida, erro, _ = rodar([sys.executable, "-m", "pytest", *opcoes_pytest(extra_path),
                            f"--junitxml={saida_xml}", *alvos],
                           codigo, env=ambiente_da_suite(codigo, extra_path, banco),
                           timeout=1800)
    resultado["saida"] = (saida + "\n" + erro)[-6000:]
    if not saida_xml.exists():
        print("  [aviso] pytest nao gerou relatorio.", file=sys.stderr)
        return resultado
    try:
        raiz = ET.parse(saida_xml).getroot()
    except ET.ParseError:
        return resultado
    for caso in raiz.iter("testcase"):
        nome = f"{caso.get('classname', '')}::{caso.get('name', '')}"
        if any(elemento.tag == "skipped" for elemento in caso):
            continue
        falhas = [elemento for elemento in caso if elemento.tag in ("failure", "error")]
        resultado["total"] += 1
        if falhas:
            resultado["falharam"] += 1
            resultado["reprovados"].add(nome)
            resultado["falhas"][nome] = (falhas[0].get("message") or "")[:500]
        else:
            resultado["passaram"] += 1
            resultado["aprovados"].add(nome)
    return resultado


def limpar_banco_medicao(caminho) -> None:
    """Remova o banco e os arquivos auxiliares criados ao seu lado."""
    if not caminho:
        return
    base = Path(caminho)
    for arquivo in (base, Path(f"{base}-journal"), Path(f"{base}-wal"),
                    Path(f"{base}-shm")):
        try:
            arquivo.unlink()
        except (FileNotFoundError, OSError):
            pass


def medir_cobertura(codigo, config: Path, testes=None, extra_path=None, banco=None):
    """Calcule o percentual de linhas de `app/` exercitado pela suíte.

    `--rcfile` fixa a configuração do instrumento: um `.coveragerc` deixado na
    pasta avaliada não pode excluir arquivos ou linhas da medição.
    """
    ambiente = ambiente_da_suite(codigo, extra_path, banco)
    arquivo_cobertura = Path(tempfile.gettempdir()) / f"cov_tcc_{os.getpid()}"
    ambiente["COVERAGE_FILE"] = str(arquivo_cobertura)
    rcfile = f"--rcfile={config / 'coveragerc'}"
    alvos = list(testes) if testes else []
    try:
        rodar([sys.executable, "-m", "coverage", "run", rcfile, "--source=app",
               "-m", "pytest", *opcoes_pytest(extra_path), *alvos],
              codigo, env=ambiente, timeout=1800)
        saida, _, _ = rodar([sys.executable, "-m", "coverage", "json", rcfile,
                             "-o", "-", "-q"], codigo, env=ambiente, timeout=300)
        dados = json.loads(saida)
        return round(dados["totals"]["percent_covered"], 1)
    except Exception as erro:  # pylint: disable=broad-except
        print(f"  [ERRO] cobertura: {erro}", file=sys.stderr)
        return None
    finally:
        for residuo in Path(tempfile.gettempdir()).glob(f"cov_tcc_{os.getpid()}*"):
            try:
                residuo.unlink()
            except OSError:
                pass


def medir_invariantes(extra_path, banco=None) -> dict:
    """Acione o oráculo sobre o mesmo banco exercitado pela suíte.

    O oráculo roda a partir da raiz do instrumento, sem a pasta avaliada no
    caminho de importação: um módulo `oracle` criado pelo agente não pode
    substituí-lo.
    """
    raiz = Path(extra_path).resolve() if extra_path else Path(__file__).resolve().parent
    ambiente = ambiente_base()
    ambiente["PYTHONPATH"] = str(raiz)
    if banco:
        ambiente["DATABASE_URL"] = f"sqlite:///{banco}"
        ambiente["SUITE_TCC"] = "1"
    codigo_py = ("import json; from oracle.invariantes import verificar; "
                 "print(json.dumps(verificar()))")
    saida, erro, _ = rodar([sys.executable, "-c", codigo_py], raiz, env=ambiente,
                           timeout=300)
    try:
        return json.loads(saida.strip().splitlines()[-1])
    except Exception:  # pylint: disable=broad-except
        print(f"  [aviso] oraculo: {erro[-300:]}", file=sys.stderr)
        return {"avaliavel": False, "motivo": "oraculo_indisponivel",
                "violadas": [], **{f"inv{n}": None for n in range(1, 9)}}


def testes_muda(caminho_classificacao, estado: str) -> set:
    """Identifique os testes que podem mudar legitimamente no estado atual."""
    if not caminho_classificacao or estado not in ("E1", "E2"):
        return set()
    try:
        with open(caminho_classificacao, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        acumulado = set()
        for chave in (["E1"] if estado == "E1" else ["E1", "E2"]):
            acumulado |= {teste for teste, classe in dados.get(chave, {}).items()
                          if classe == "MUDA"}
        return acumulado
    except Exception:  # pylint: disable=broad-except
        return set()


def estado_anterior(app, estado, pasta_detalhes: Path):
    """Recupere os dados do estado anterior, caso estejam disponíveis."""
    if estado not in ORDEM_ESTADOS:
        return None
    idx = ORDEM_ESTADOS.index(estado)
    if idx == 0:
        return None
    anterior = pasta_detalhes / f"{app}-{ORDEM_ESTADOS[idx - 1]}.json"
    if not anterior.exists():
        return None
    try:
        with open(anterior, encoding="utf-8") as arquivo_anterior:
            return json.load(arquivo_anterior)
    except (OSError, json.JSONDecodeError):
        return None


def sufixo(nome: str) -> str:
    """Normalize o nome do teste: módulo e função, sem o prefixo do pacote."""
    return nome.split("::")[0].split(".")[-1] + "::" + nome.split("::")[-1]


def main():
    ap = argparse.ArgumentParser(description="Coleta de indicadores do TCC (v2).")
    ap.add_argument("--app", required=True, help="Identificador da aplicacao (ex: r1)")
    ap.add_argument("--estado", required=True, choices=ORDEM_ESTADOS)
    ap.add_argument("--codigo", default=".", help="Pasta do codigo avaliado")
    ap.add_argument("--saida", default="resultados.csv")
    ap.add_argument("--testes", nargs="*", default=None,
                    help="caminhos EXTERNOS das suites (oracle/...)")
    ap.add_argument("--db", default=None,
                    help="caminho do banco avaliado; o mesmo entregue a suite")
    ap.add_argument("--classificacao", default=None,
                    help="classificacao.json, para distinguir regressao real")
    ap.add_argument("--extra-path", default=None,
                    help="raiz do instrumento (contem oracle/ e pytest.ini)")
    ap.add_argument("--esperado", type=int, default=None,
                    help="numero exato de testes que a coleta deve encontrar")
    ap.add_argument("--config", default=str(CONFIG_PADRAO),
                    help="pasta com pylintrc, bandit.ini e coveragerc do instrumento")
    args = ap.parse_args()

    codigo = Path(args.codigo).resolve()
    if not codigo.is_dir():
        sys.exit(f"ERRO: pasta nao encontrada: {codigo}")
    config = Path(args.config).resolve()
    for exigido in ("pylintrc", "bandit.ini", "coveragerc"):
        if not (config / exigido).is_file():
            sys.exit(f"ERRO: {exigido} ausente em {config}")

    saida_csv = Path(args.saida).resolve()
    detalhes = saida_csv.parent / "detalhes"
    detalhes.mkdir(parents=True, exist_ok=True)
    neutra = Path(tempfile.mkdtemp(prefix="medir_neutra_"))

    print(f"\nMedindo {args.app} no estado {args.estado}")
    print(f"Codigo em: {codigo}\n")

    arquivos = alvos_python(codigo)
    print(f"  {len(arquivos)} arquivos .py encontrados")

    print("  Pylint...")
    pl = medir_pylint(codigo, arquivos, config)
    print("  Radon...")
    rd = medir_radon(arquivos, neutra)
    print("  Bandit...")
    bd = medir_bandit(arquivos, config, neutra)

    limpar_banco_medicao(args.db)
    importa, erro_importacao, travou = verificar_importacao(codigo, args.extra_path,
                                                            args.db)
    limpar_banco_medicao(args.db)
    if travou:
        print("  [aviso] a importacao da aplicacao nao terminou; suite nao executada",
              file=sys.stderr)
        cobertura = None
        pt = {"total": 0, "passaram": 0, "falharam": 0, "aprovados": set(),
              "reprovados": set(), "falhas": {}, "saida": erro_importacao}
        inv = {"avaliavel": False, "motivo": "aplicacao_nao_importa", "violadas": [],
               **{f"inv{n}": None for n in range(1, 9)}}
    else:
        # A cobertura executa a suíte e popula o banco. O pytest canônico deve
        # começar com uma base vazia, para que todos os estados partam de
        # condições iniciais equivalentes.
        print("  cobertura...")
        cobertura = medir_cobertura(codigo, config, testes=args.testes,
                                    extra_path=args.extra_path, banco=args.db)
        limpar_banco_medicao(args.db)
        print("  pytest...")
        pt = medir_pytest(codigo, detalhes / f"{args.app}-{args.estado}-junit.xml",
                          testes=args.testes, extra_path=args.extra_path, banco=args.db)
        # O oráculo roda depois da suíte, pois são os testes que preenchem o banco.
        print("  invariantes...")
        inv = medir_invariantes(args.extra_path, banco=args.db)
    try:
        neutra.rmdir()
    except OSError:
        pass

    ant = estado_anterior(args.app, args.estado, detalhes)
    if ant:
        antes = set(ant.get("testes_aprovados", []))
        regredidos = sorted(antes - pt["aprovados"])
    else:
        regredidos = []
    muda_norm = {sufixo(n) for n in testes_muda(args.classificacao, args.estado)}
    regredidos_reais = [t for t in regredidos if sufixo(t) not in muda_norm]
    legitimas = [t for t in regredidos if sufixo(t) in muda_norm]

    # Uma aplicação que não importa não deixa a suíte nem o oráculo operarem:
    # isso é resultado do agente, não falha do instrumento.
    if args.esperado is not None:
        coleta_ok = pt["total"] == args.esperado
    else:
        coleta_ok = pt["total"] > 0
    dinamicas_aplicaveis = importa
    ferramentas_com_falha = [nome for nome, ok in (
        ("pylint", pl["valido"]), ("radon", rd["valido"]), ("bandit", bd["valido"]),
        ("coverage", cobertura is not None or not dinamicas_aplicaveis),
        ("pytest", coleta_ok or not dinamicas_aplicaveis),
        ("oraculo", inv.get("avaliavel", False) or not dinamicas_aplicaveis),
    ) if not ok]

    linha = {
        "app": args.app,
        "estado": args.estado,
        "data_hora": datetime.now().isoformat(timespec="seconds"),
        "arquivos_py": len(arquivos),
        "linhas_codigo": contar_linhas(arquivos),
        "pylint_convention": pl["convention"],
        "pylint_refactor": pl["refactor"],
        "pylint_warning": pl["warning"],
        "pylint_error": pl["error"],
        "pylint_total": pl["total"],
        "pylint_nota": pl["nota"],
        "cc_media": rd["cc_media"],
        "cc_maxima": rd["cc_maxima"],
        "funcoes_cc_acima_10": rd["acima_10"],
        "total_funcoes": rd["total_funcoes"],
        "mi_medio": rd["mi_medio"],
        "mi_minimo": rd["mi_minimo"],
        "bandit_alta": bd["alta"],
        "bandit_media": bd["media"],
        "bandit_baixa": bd["baixa"],
        "bandit_total": bd["total"],
        "testes_total": pt["total"],
        "testes_passaram": pt["passaram"],
        "testes_falharam": pt["falharam"],
        "taxa_aprovacao_pct": round(100 * pt["passaram"] / pt["total"], 1) if pt["total"] else 0,
        "cobertura_pct": "" if cobertura is None else cobertura,
        "regressoes": len(regredidos),
        "regressoes_reais": len(regredidos_reais),
        "falhas_legitimas": len(legitimas),
        "testes_regredidos": "; ".join(regredidos_reais),
        "inv_avaliavel": "sim" if inv.get("avaliavel") else "nao",
        **{f"inv{n}": ("" if inv.get(f"inv{n}") is None
                       else ("ok" if inv.get(f"inv{n}") else "violada"))
           for n in range(1, 9)},
        "invariantes_violadas": "; ".join(inv.get("violadas", [])),
        "instrumentos_validos": "nao" if ferramentas_com_falha else "sim",
        "ferramentas_com_falha": "; ".join(ferramentas_com_falha),
        "testes_esperados": "" if args.esperado is None else args.esperado,
        "app_importa": "sim" if importa else "nao",
        "pylint_supressoes": pl["supressoes"],
        "pylint_config_agente": configuracoes_do_agente(codigo),
        "bandit_nosec": bd["nosec"],
        "cobertura_pragmas": contar_padrao(arquivos, r"pragma:\s*no\s*cover"),
    }

    existe = saida_csv.exists()
    with open(saida_csv, "a", newline="", encoding="utf-8") as arquivo_csv:
        escritor_csv = csv.DictWriter(arquivo_csv, fieldnames=COLUNAS)
        if not existe:
            escritor_csv.writeheader()
        escritor_csv.writerow(linha)

    with open(detalhes / f"{args.app}-{args.estado}.json", "w", encoding="utf-8") as arquivo_json:
        json.dump({
            **linha,
            "testes_aprovados": sorted(pt["aprovados"]),
            "testes_reprovados": sorted(pt["reprovados"]),
            "falhas": pt["falhas"],
            "erro_importacao": erro_importacao,
            "saida_pytest": pt["saida"] if (not coleta_ok or not importa) else "",
            "pylint_por_simbolo": pl["por_simbolo"],
            "pylint_suprimidas_por_simbolo": pl["suprimidas_por_simbolo"],
            "invariantes_detalhes": inv.get("detalhes", []),
        }, arquivo_json, indent=2, ensure_ascii=False)

    print("\n" + "=" * 52)
    print(f"  Linhas de codigo .......... {linha['linhas_codigo']}")
    print(f"  Pylint (C/R/W/E) .......... {pl['convention']}/{pl['refactor']}/{pl['warning']}/{pl['error']}")
    print(f"  Pylint suprimidas ......... {pl['supressoes']}")
    print(f"  Nota Pylint ............... {pl['nota'] or 'n/d'}")
    print(f"  Complexidade media / max .. {rd['cc_media']} / {rd['cc_maxima']}")
    print(f"  Indice manutenibilidade ... {rd['mi_medio']} (min {rd['mi_minimo']})")
    print(f"  Bandit (A/M/B) ............ {bd['alta']}/{bd['media']}/{bd['baixa']} (nosec {bd['nosec']})")
    print(f"  Aplicacao importa ......... {'sim' if importa else 'NAO: ' + erro_importacao}")
    print(f"  Cobertura ................. {'NA' if cobertura is None else str(cobertura) + chr(37)}")
    print(f"  Invariantes ............... {inv.get('violadas') if inv.get('avaliavel') else 'NAO AVALIAVEL'}")
    print(f"  Testes .................... {pt['passaram']}/{pt['total']}"
          f"{'' if args.esperado is None else f' (esperado {args.esperado})'}")
    print(f"  REGRESSOES ................ {len(regredidos)}")
    for teste_regredido in regredidos[:10]:
        print(f"      - {teste_regredido}")
    print(f"  Instrumentos validos ...... {linha['instrumentos_validos']}"
          f"{'' if not ferramentas_com_falha else ' (' + linha['ferramentas_com_falha'] + ')'}")
    print("=" * 52)
    print(f"\nGravado em {saida_csv}\n")


if __name__ == "__main__":
    main()
