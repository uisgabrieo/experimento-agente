"""Versionamento, medições externas e relatórios do estudo (instrumento v2).

Toda execução de instrumento acontece sobre uma cópia do commit avaliado,
extraída com `git archive` para uma pasta temporária fora da área do agente.
A área de trabalho do agente nunca recebe banco, cache ou relatório dos
instrumentos, e o que se mede é exatamente o que foi congelado.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

LIMITE_RELATORIO = 6000

# Módulos sem os quais a medição ficaria inválida. Se faltarem, quase sempre é
# porque a venv não foi ativada na janela do PowerShell.
FERRAMENTAS_EXIGIDAS = ("pytest", "hypothesis", "coverage", "pylint", "radon", "bandit",
                        "fastapi", "sqlalchemy", "pydantic", "httpx")


def ferramentas_ausentes() -> list[str]:
    """Devolva os módulos do instrumento que o Python atual não encontra."""
    import importlib.util  # pylint: disable=import-outside-toplevel
    return [nome for nome in FERRAMENTAS_EXIGIDAS if importlib.util.find_spec(nome) is None]


# ---------------------------------------------------------------- Git

def git(pasta: Path, *args: str) -> str:
    """Execute um comando Git na pasta e devolva a saída padrão."""
    processo = subprocess.run(["git", *args], cwd=pasta, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    if (processo.returncode != 0
            and "nothing to commit" not in (processo.stdout + processo.stderr)):
        print(f"    [git] {' '.join(args)}: {processo.stderr.strip()[:160]}",
              file=sys.stderr)
    return processo.stdout.strip()


def git_codigo(pasta: Path, *args: str) -> int:
    """Execute um comando Git e devolva apenas o código de término."""
    return subprocess.run(["git", *args], cwd=pasta, capture_output=True).returncode


def etiqueta_existe(pasta: Path, etiqueta: str) -> bool:
    return git_codigo(pasta, "rev-parse", "-q", "--verify", f"refs/tags/{etiqueta}") == 0


def commit_de(pasta: Path, referencia: str) -> str:
    return git(pasta, "rev-parse", f"{referencia}^{{commit}}")


def registrar_commit(pasta: Path) -> str:
    """Registre tudo o que mudou em um commit opaco e devolva o HEAD."""
    git(pasta, "add", "-A")
    git(pasta, "commit", "-q", "-m", "snapshot")
    return commit_de(pasta, "HEAD")


def congelar(pasta: Path, etiqueta: str) -> str:
    """Registre o estado atual em commit e etiqueta; nunca move etiqueta existente."""
    if etiqueta_existe(pasta, etiqueta):
        raise RuntimeError(f"a etiqueta {etiqueta} ja existe; nada foi alterado")
    commit = registrar_commit(pasta)
    git(pasta, "tag", etiqueta)
    return commit


def area_limpa(pasta: Path) -> bool:
    return git(pasta, "status", "--porcelain", "--untracked-files=all") == ""


def restaurar_ultimo_commit(pasta: Path) -> None:
    """Descarte edições não registradas, como as de uma invocação interrompida."""
    git(pasta, "reset", "-q", "--hard", "HEAD")
    git(pasta, "clean", "-q", "-fd")


def dispersao(pasta: Path, anterior: str, atual: str, caminho: str | None = None) -> dict:
    """Calcule quantos arquivos e linhas mudaram entre duas referências.

    Com `caminho` (por exemplo, "app"), conta só o que está sob esse caminho.
    """
    argumentos = ["diff", "--numstat", anterior, atual] + (["--", caminho] if caminho else [])
    saida = git(pasta, *argumentos)
    arquivos = adicionadas = removidas = 0
    for linha in saida.splitlines():
        partes = linha.split("\t")
        if len(partes) != 3:
            continue
        arquivos += 1
        adicionadas += int(partes[0]) if partes[0].isdigit() else 0
        removidas += int(partes[1]) if partes[1].isdigit() else 0
    return {"arquivos_tocados": arquivos, "linhas_adicionadas": adicionadas,
            "linhas_removidas": removidas}


# ---------------------------------------------------------------- cópias de trabalho

def remover_arvore(caminho: Path) -> None:
    """Remova um diretório, inclusive arquivos somente leitura (Windows)."""
    def tratar(funcao, alvo, _excecao):
        try:
            os.chmod(alvo, stat.S_IWRITE)
            funcao(alvo)
        except OSError:
            pass
    if not caminho.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(caminho, onexc=tratar)
    else:
        shutil.rmtree(caminho, onerror=tratar)


class CopiaDoCommit:
    """Extraia um commit para pasta temporária e remova-a ao final.

    Uso: `with CopiaDoCommit(area, referencia) as copia: copia.codigo, copia.banco`.
    """

    def __init__(self, area: Path, referencia: str):
        self.area = area
        self.referencia = referencia
        self.pasta: Path | None = None

    def __enter__(self):
        self.pasta = Path(tempfile.mkdtemp(prefix="tcc_v2_"))
        processo = subprocess.run(["git", "archive", "--format=tar", self.referencia],
                                  cwd=self.area, capture_output=True)
        if processo.returncode != 0:
            raise RuntimeError(f"git archive {self.referencia}: "
                               f"{processo.stderr.decode(errors='replace')[:200]}")
        self.codigo.mkdir()
        with tarfile.open(fileobj=io.BytesIO(processo.stdout)) as pacote:
            pacote.extractall(self.codigo, filter="data")
        return self

    @property
    def codigo(self) -> Path:
        return self.pasta / "codigo"

    @property
    def banco(self) -> Path:
        return self.pasta / "avaliacao.db"

    def __exit__(self, *_):
        if self.pasta is not None:
            remover_arvore(self.pasta)


# ---------------------------------------------------------------- suíte e oráculo

def _ambiente(caminhos: list[str], banco: Path | None) -> dict:
    ambiente = dict(os.environ)
    for variavel in ("CHAVE_COORDENADOR", "CHAVE_PROFISSIONAL", "PYTEST_ADDOPTS",
                     "PYTEST_PLUGINS", "PYLINTRC", "RADONCFG", "COVERAGE_RCFILE"):
        ambiente.pop(variavel, None)
    ambiente["PYTHONPATH"] = os.pathsep.join(caminhos)
    ambiente["PYTHONUTF8"] = "1"
    ambiente["PYTHONIOENCODING"] = "utf-8"
    if banco is not None:
        ambiente["DATABASE_URL"] = f"sqlite:///{banco}"
        ambiente["SUITE_TCC"] = "1"
    return ambiente


def limpar_banco(banco: Path) -> None:
    for arquivo in (banco, Path(f"{banco}-journal"), Path(f"{banco}-wal"),
                    Path(f"{banco}-shm")):
        try:
            arquivo.unlink()
        except OSError:
            pass


def rodar_suite(raiz: Path, codigo: Path, suites: list[str], junit: Path,
                banco: Path, esperado: int) -> dict:
    """Execute as suítes externas contra a cópia da aplicação.

    A coleta só é válida com exatamente `esperado` testes. Quando a aplicação
    não importa, a coleta é zero; isso é resultado do agente, e o erro de
    importação segue no relatório para que ele possa corrigi-lo.
    """
    limpar_banco(banco)
    ambiente = _ambiente([str(codigo), str(raiz)], banco)
    importacao = subprocess.run([sys.executable, "-c", "import app.main"], cwd=codigo,
                                env=ambiente, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=300)
    limpar_banco(banco)
    if junit.exists():
        junit.unlink()
    alvos = [str(raiz / "oracle" / nome) for nome in suites]
    processo = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "-c", str(raiz / "pytest.ini"), f"--rootdir={raiz}",
         f"--junitxml={junit}", *alvos],
        cwd=codigo, env=ambiente, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=1800)
    aprovados, reprovados = set(), set()
    if junit.exists():
        try:
            for caso in ET.parse(junit).getroot().iter("testcase"):
                nome = f"{caso.get('classname', '')}::{caso.get('name', '')}"
                if any(elemento.tag == "skipped" for elemento in caso):
                    continue
                if any(elemento.tag in ("failure", "error") for elemento in caso):
                    reprovados.add(nome)
                else:
                    aprovados.add(nome)
        except ET.ParseError:
            pass
    coletados = len(aprovados) + len(reprovados)
    erro_importacao = ""
    if importacao.returncode != 0:
        linhas = [linha for linha in importacao.stderr.splitlines() if linha.strip()]
        erro_importacao = "\n".join(linhas[-25:])
    return {"aprovados": aprovados, "reprovados": reprovados, "coletados": coletados,
            "esperado": esperado, "valida": junit.exists() and coletados == esperado,
            "importa": importacao.returncode == 0, "erro_importacao": erro_importacao,
            "saida": (processo.stdout + "\n" + processo.stderr)[-3000:]}


def verificar_invariantes(raiz: Path, banco: Path) -> dict:
    """Execute o oráculo sobre o banco usado pela suíte.

    Roda a partir da raiz do instrumento, sem a cópia da aplicação no caminho
    de importação: nenhum módulo do agente pode substituir o oráculo.
    """
    ambiente = _ambiente([str(raiz)], banco)
    codigo = ("import json; from oracle.invariantes import verificar; "
              "print(json.dumps(verificar()))")
    processo = subprocess.run([sys.executable, "-c", codigo], cwd=raiz, env=ambiente,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=300)
    try:
        return json.loads(processo.stdout.strip().splitlines()[-1])
    except Exception:  # pylint: disable=broad-except
        return {"avaliavel": False, "motivo": "oraculo_falhou", "violadas": [],
                "erro": processo.stderr[-300:]}


# ---------------------------------------------------------------- relatórios ao agente

def _bloco_coleta(resultado: dict, titulo: str) -> list[str]:
    """Linhas do relatório para uma suíte, inclusive quando ela não pôde rodar."""
    linhas = []
    if not resultado["importa"]:
        linhas.append(f"{titulo}: nao executados, porque a aplicacao nao pode ser importada.")
        linhas.append("Erro ao importar app.main:")
        linhas += [f"  {linha}" for linha in resultado["erro_importacao"].splitlines()]
        return linhas
    linhas.append(f"{titulo}: {len(resultado['aprovados'])} aprovados / "
                  f"{resultado['coletados']}")
    if resultado["coletados"] != resultado["esperado"]:
        linhas.append("A coleta dos testes falhou. Saida do executor de testes:")
        linhas += [f"  {linha}" for linha in resultado["saida"].splitlines()[-30:]]
    return linhas


def relatorio_estruturado(novo: dict | None, base: dict, muda: set[str],
                          invariantes: dict, iteracao: int) -> str:
    """Monte o relatório de testes e invariantes enviado ao agente.

    Como na versão 1, o agente recebe os nomes dos testes, não o código nem as
    mensagens de asserção. Mudanças em relação à versão 1: testes que falham
    são chamados de reprovados, e não de regressões, pois podem falhar desde o
    primeiro estado; e uma coleta impossível mostra o erro, em vez de "0 / 0".
    """
    def sufixo(nome: str) -> str:
        return nome.split("::")[0].split(".")[-1] + "::" + nome.split("::")[-1]

    linhas = [f"RELATORIO DE VERIFICACAO - iteracao {iteracao}", ""]
    if novo is not None:
        linhas += _bloco_coleta(novo, "Testes do novo requisito")
        if novo["reprovados"]:
            linhas.append("Reprovados:")
            linhas += [f"  - {nome}" for nome in sorted(novo["reprovados"])]
        linhas.append("")
    muda_norm = {sufixo(nome) for nome in muda}
    reprovados = sorted(nome for nome in base["reprovados"] if sufixo(nome) not in muda_norm)
    linhas += _bloco_coleta(base, "Testes do comportamento existente")
    if reprovados:
        linhas.append("Reprovados:")
        linhas += [f"  - {nome}" for nome in reprovados]
    linhas.append("")
    if invariantes.get("avaliavel"):
        linhas.append(f"Invariantes violadas: {invariantes.get('violadas', [])}")
    else:
        linhas.append("Invariantes: nao avaliaveis (o banco nao foi criado pela aplicacao)")
    return "\n".join(linhas)


def relatorios_estaticos(codigo: Path, config: Path) -> str:
    """Reúna Pylint, Radon e Bandit da cópia avaliada, com a configuração do instrumento.

    Mesmo conteúdo da versão 1 (texto das ferramentas, até 6000 caracteres
    cada). Diferença: arquivos de configuração deixados pelo agente na área de
    trabalho não alteram o relatório; o Radon e o Bandit rodam numa pasta
    neutra, e o prefixo absoluto é retirado dos caminhos exibidos.
    """
    neutra = Path(tempfile.mkdtemp(prefix="tcc_v2_neutra_"))
    prefixo = str(codigo.resolve()) + os.sep
    arquivos = sorted(str(p.resolve()) for p in (codigo / "app").rglob("*.py")
                      if "__pycache__" not in p.parts) if (codigo / "app").is_dir() else []
    ambiente = _ambiente([str(codigo)], None)
    ambiente_neutro = dict(ambiente, HOME=str(neutra), USERPROFILE=str(neutra))
    comandos = [
        ("PYLINT", [sys.executable, "-m", "pylint", "app/", f"--rcfile={config / 'pylintrc'}",
                    "--persistent=n", "--output-format=text"], codigo, ambiente),
        ("COMPLEXIDADE", [sys.executable, "-m", "radon", "cc", *arquivos, "-s", "-n", "C"],
         neutra, ambiente_neutro),
        ("SEGURANCA", [sys.executable, "-m", "bandit", "-q", "--ini",
                       str(config / "bandit.ini"), *arquivos], neutra, ambiente_neutro),
    ]
    partes = []
    try:
        for rotulo, comando, pasta, env in comandos:
            if rotulo != "PYLINT" and not arquivos:
                partes.append(f"===== {rotulo} =====\nsem ocorrencias")
                continue
            processo = subprocess.run(comando, cwd=pasta, env=env, capture_output=True,
                                      text=True, encoding="utf-8", errors="replace",
                                      timeout=600)
            texto = (processo.stdout or "").replace(prefixo, "").strip()[:LIMITE_RELATORIO]
            partes.append(f"===== {rotulo} =====\n{texto or 'sem ocorrencias'}")
    finally:
        remover_arvore(neutra)
    return "\n\n".join(partes)


# ---------------------------------------------------------------- medição

def medir(raiz: Path, app: str, estado: str, codigo: Path, banco: Path,
          saida_csv: Path, suites: list[str], esperado: int) -> dict:
    """Meça a cópia da aplicação com o medidor do instrumento e devolva os detalhes."""
    alvos = [str(raiz / "oracle" / nome) for nome in suites]
    processo = subprocess.run(
        [sys.executable, str(raiz / "medir.py"), "--app", app, "--estado", estado,
         "--codigo", str(codigo), "--saida", str(saida_csv),
         "--testes", *alvos, "--extra-path", str(raiz),
         "--classificacao", str(raiz / "artefatos" / "classificacao.json"),
         "--db", str(banco), "--esperado", str(esperado),
         "--config", str(raiz / "config")],
        cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
    detalhe = saida_csv.parent / "detalhes" / f"{app}-{estado}.json"
    if detalhe.exists():
        return json.loads(detalhe.read_text(encoding="utf-8"))
    print(f"    [ERRO] medicao de {app} {estado} nao gerou detalhes:\n"
          f"{processo.stderr[-800:]}", file=sys.stderr)
    return {}
