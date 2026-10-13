"""Reavalia os estados congelados da coleta 1 com o instrumento v2.

Nenhuma chamada ao agente é feita. Nada é escrito na pasta da coleta 1 nem em
C:\\execucoes: os commits são lidos com `git archive` e medidos em pastas
temporárias.

Para cada repetição e estado, o script:
1. localiza a etiqueta da coleta 1 e confere o commit contra `estados.csv`;
2. extrai o commit em pasta temporária;
3. mede com o `medir.py` desta pasta, a suíte auditada e a configuração fixa.

Uso, na pasta tcc-v2, com a venv ativa:
    python reavaliar_v1.py --todas
    python reavaliar_v1.py --rep 4

Por padrão a coleta 1 é procurada em ..\\tcc (estados.csv) e as áreas de
trabalho em C:\\execucoes; use --coleta1 e --base para outros caminhos.

Saídas, todas em reavaliacao-v1\\:
    resultados.csv    uma linha por estado, colunas do medidor v2
    detalhes\\         JUnit e JSON por estado
    registro.csv      etiqueta, commit e conferência por estado
    manifesto.json    SHA-256 do instrumento, versões e ambiente
    resumo.txt        a tabela impressa ao final
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import platform
import subprocess
import sys
import time
from datetime import datetime
from importlib import metadata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from orq.estados import (CopiaDoCommit, ferramentas_ausentes, medir,  # noqa: E402
                         remover_arvore)

SAIDA = RAIZ / "reavaliacao-v1"
ESTADOS = ["M0", "M1", "M2", "M3", "M4", "M5", "E1", "E2"]
SUITES = {"M": ["base", "propriedades"], "E1": ["base", "propriedades", "e1"],
          "E2": ["base", "propriedades", "e1", "e2"]}
ESPERADO = {"M": 55, "E1": 64, "E2": 80}
FERRAMENTAS = ["pytest", "hypothesis", "coverage", "pylint", "astroid", "radon",
               "bandit", "fastapi", "starlette", "pydantic", "pydantic-core",
               "sqlalchemy", "httpx"]


def pasta_da_repeticao(base: Path, rep: int) -> Path:
    """Mesma regra da coleta 1 (sal 'escala-')."""
    return base / hashlib.sha256(f"escala-{rep}".encode()).hexdigest()[:10]


def etiqueta(rep: int, estado: str) -> str:
    """Mesma regra da coleta 1."""
    return "s" + hashlib.sha256(f"{rep}-{estado}".encode()).hexdigest()[:12]


def git(repo: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def commits_registrados(coleta1: Path) -> dict:
    arquivo = coleta1 / "estados.csv"
    if not arquivo.exists():
        return {}
    texto = arquivo.read_text(encoding="utf-8-sig")
    return {(int(linha["repeticao"]), linha["estado"]): linha["commit_sha"]
            for linha in csv.DictReader(io.StringIO(texto))}


def sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def gravar_manifesto(coleta1: Path, base: Path) -> None:
    arquivos = sorted(p for padrao in ("oracle/**/*.py", "config/*", "medir.py",
                                       "reavaliar_v1.py", "orq/estados.py", "pytest.ini",
                                       "artefatos/classificacao.json")
                      for p in RAIZ.glob(padrao) if p.is_file() and "__pycache__" not in p.parts)
    versoes = {}
    for nome in FERRAMENTAS:
        try:
            versoes[nome] = metadata.version(nome)
        except metadata.PackageNotFoundError:
            versoes[nome] = "ausente"
    (SAIDA / "manifesto.json").write_text(json.dumps({
        "instrumento": "v2",
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "fuso_horario": time.strftime("%z"),
        "python": platform.python_version(),
        "sistema": f"{platform.system()} {platform.release()}",
        "ferramentas": versoes,
        "coleta1": str(coleta1), "areas_de_trabalho": str(base),
        "arquivos": {str(p.relative_to(RAIZ)).replace("\\", "/"): sha256(p) for p in arquivos},
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def reavaliar(rep: int, base: Path, registrados: dict) -> list[dict]:
    repo = pasta_da_repeticao(base, rep)
    if not (repo / ".git").exists():
        return []
    existentes = set(git(repo, "tag", "-l").stdout.split())
    registros = []
    print(f"\nr{rep}  ({repo.name})")
    for estado in ESTADOS:
        rotulo = etiqueta(rep, estado)
        if rotulo not in existentes:
            print(f"  {estado}  nao coletado")
            continue
        commit = git(repo, "rev-parse", f"{rotulo}^{{commit}}").stdout.strip()[:12]
        registrado = registrados.get((rep, estado), "")
        confere = ("sim" if registrado and commit.startswith(registrado[:12])
                   else ("sem_registro" if not registrado else "NAO"))
        grupo = "M" if estado.startswith("M") else estado
        inicio = time.time()
        with CopiaDoCommit(repo, rotulo) as copia:
            dados = medir(RAIZ, f"r{rep}", estado, copia.codigo, copia.banco,
                          SAIDA / "resultados.csv", SUITES[grupo], ESPERADO[grupo])
        coletados = int(dados.get("testes_total") or 0)
        invariantes = ("NAO AVALIAVEL" if dados.get("inv_avaliavel") != "sim"
                       else (dados.get("invariantes_violadas") or "ok"))
        print(f"  {estado}  {commit}  {dados.get('testes_passaram', '?')}/{coletados}"
              f"  pylint {dados.get('pylint_total', '?')} (+{dados.get('pylint_supressoes', '?')} suprimidas)"
              f"  cobertura {dados.get('cobertura_pct', '?')}  invariantes {invariantes}"
              f"{'' if dados.get('app_importa') == 'sim' else '  APLICACAO NAO IMPORTA'}"
              f"{'' if confere == 'sim' else f'  <- commit {confere}'}"
              f"  ({time.time() - inicio:.0f}s)")
        registros.append({
            "repeticao": rep, "estado": estado, "etiqueta": rotulo, "commit": commit,
            "commit_em_estados_csv": registrado, "commit_confere": confere,
            "coletados": coletados, "esperado": ESPERADO[grupo],
            "app_importa": dados.get("app_importa", ""),
            "instrumentos_validos": dados.get("instrumentos_validos", ""),
        })
    return registros


def resumo() -> str:
    """Tabela final: testes aprovados/coletados e Pylint visível + suprimido."""
    arquivo = SAIDA / "resultados.csv"
    if not arquivo.exists():
        return "(sem resultados)"
    linhas = list(csv.DictReader(io.StringIO(arquivo.read_text(encoding="utf-8"))))
    por = {(l["app"], l["estado"]): l for l in linhas}
    reps = sorted({l["app"] for l in linhas}, key=lambda a: int(a[1:]))
    saida = ["TESTES (aprovados/coletados)", "rep   " + "".join(f"{e:>8}" for e in ESTADOS)]
    for app in reps:
        celulas = []
        for estado in ESTADOS:
            l = por.get((app, estado))
            celulas.append(f"{l['testes_passaram']}/{l['testes_total']}" if l else "-")
        saida.append(f"{app:<6}" + "".join(f"{c:>8}" for c in celulas))
    saida += ["", "PYLINT (ocorrencias visiveis + suprimidas por comentario)",
              "rep   " + "".join(f"{e:>8}" for e in ESTADOS)]
    for app in reps:
        celulas = []
        for estado in ESTADOS:
            l = por.get((app, estado))
            celulas.append(f"{l['pylint_total']}+{l['pylint_supressoes']}" if l else "-")
        saida.append(f"{app:<6}" + "".join(f"{c:>8}" for c in celulas))
    return "\n".join(saida)


def main() -> None:
    analisador = argparse.ArgumentParser()
    grupo = analisador.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--todas", action="store_true", help="refaz tudo, repeticoes 1 a 10")
    grupo.add_argument("--rep", type=int, help="apenas uma repeticao")
    analisador.add_argument("--coleta1", default=str(RAIZ.parent / "tcc"),
                            help="pasta da pesquisa da coleta 1 (contem estados.csv)")
    analisador.add_argument("--base", default=r"C:\execucoes",
                            help="pasta das areas de trabalho da coleta 1")
    argumentos = analisador.parse_args()

    ausentes = ferramentas_ausentes()
    if ausentes:
        sys.exit("ferramentas nao encontradas neste Python (" + ", ".join(ausentes)
                 + "). Ative a venv da coleta 1 (Activate.ps1) e rode de novo.")
    coleta1, base = Path(argumentos.coleta1), Path(argumentos.base)
    if not (coleta1 / "estados.csv").exists():
        sys.exit(f"estados.csv nao encontrado em {coleta1}. Use --coleta1 <pasta da coleta 1>.")
    if not base.is_dir():
        sys.exit(f"pasta das areas de trabalho nao encontrada: {base}. Use --base <pasta>.")
    SAIDA.mkdir(exist_ok=True)
    if argumentos.todas:
        for alvo in (SAIDA / "resultados.csv", SAIDA / "registro.csv", SAIDA / "resumo.txt"):
            alvo.unlink(missing_ok=True)
        remover_arvore(SAIDA / "detalhes")
    gravar_manifesto(coleta1, base)

    registrados = commits_registrados(coleta1)
    repeticoes = range(1, 11) if argumentos.todas else [argumentos.rep]
    registros = []
    for rep in repeticoes:
        registros += reavaliar(rep, base, registrados)

    if registros:
        novo = not (SAIDA / "registro.csv").exists()
        with open(SAIDA / "registro.csv", "a", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=list(registros[0]))
            if novo:
                escritor.writeheader()
            escritor.writerows(registros)

    texto = resumo()
    (SAIDA / "resumo.txt").write_text(texto + "\n", encoding="utf-8")
    problemas = [r for r in registros if r["commit_confere"] != "sim"]
    print("\n" + texto)
    print(f"\n{len(registros)} estados reavaliados.")
    print(f"Commits conferidos contra estados.csv: {len(registros) - len(problemas)}/{len(registros)}")
    invalidos = [r for r in registros if r["instrumentos_validos"] != "sim"]
    print(f"Medicoes com instrumento invalido: {len(invalidos)}")
    for r in invalidos:
        print(f"  r{r['repeticao']} {r['estado']}: coletados {r['coletados']}/{r['esperado']}")
    print(f"Saida: {SAIDA}")


if __name__ == "__main__":
    main()
