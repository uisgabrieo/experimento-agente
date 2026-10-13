#!/usr/bin/env python3
"""Registra o ambiente da coleta 2 antes da primeira execução real.

Uso (depois de `python orquestrador.py --verificar-agente`):
    python manifesto.py

Cria `manifesto-experimento.json` com as versões das ferramentas, o SHA-256
dos artefatos congelados, a versão do Claude Code, o conteúdo relevante de
`~/.claude/settings.json` e a identificação do ambiente. O orquestrador recusa
iniciar a coleta sem esse arquivo e recusa continuar se a versão do Claude Code
mudar.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PADROES = ["artefatos/*", "config/*", "oracle/*.py", "oracle/base/*.py",
           "oracle/propriedades/*.py", "oracle/e1/*.py", "oracle/e2/*.py",
           "validacao_oraculo/*.py", "orq/*.py", "orquestrador.py", "medir.py",
           "manifesto.py", "reavaliar_v1.py", "requirements.txt", "pytest.ini",
           "metodologia/protocolo-execucao.md"]

FERRAMENTAS = ["pytest", "hypothesis", "coverage", "pylint", "astroid", "radon",
               "bandit", "fastapi", "starlette", "pydantic", "pydantic-core",
               "sqlalchemy", "httpx", "uvicorn"]


def hash_arquivo(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest() if caminho.exists() else "AUSENTE"


def versao_pacote(nome: str) -> str:
    try:
        from importlib.metadata import version
        return version(nome)
    except Exception:  # pylint: disable=broad-except
        return "nao instalado"


def comando(*args) -> str:
    try:
        processo = subprocess.run(args, capture_output=True, text=True, timeout=30,
                                  encoding="utf-8", errors="replace")
        return ((processo.stdout or processo.stderr).strip().splitlines() or [""])[0]
    except Exception:  # pylint: disable=broad-except
        return "indisponivel"


def configuracao_do_agente() -> dict:
    """Leia de ~/.claude/settings.json o que influencia o agente."""
    caminho = Path.home() / ".claude" / "settings.json"
    if not caminho.exists():
        return {"arquivo": str(caminho), "existe": False}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        return {"arquivo": str(caminho), "existe": True, "erro": str(erro)}
    return {"arquivo": str(caminho), "existe": True,
            "model": dados.get("model"), "effortLevel": dados.get("effortLevel"),
            "env": dados.get("env", {}), "permissions": dados.get("permissions"),
            "autoUpdatesChannel": dados.get("autoUpdatesChannel")}


def main():
    raiz = Path(__file__).resolve().parent
    manifesto = {
        "coleta": "2",
        "data_geracao": datetime.now().isoformat(timespec="seconds"),
        "ambiente": {
            "python": sys.version.split()[0],
            "sistema_operacional": f"{platform.system()} {platform.release()}",
            "arquitetura": platform.machine(),
        },
        "agente": {
            "claude_code": comando("claude", "--version"),
            "modelo_solicitado": "opus (--model opus)",
            "modelo_efetivo": "ver coluna 'modelos' de coleta/interacoes.csv",
            "modo_de_permissao": "acceptEdits",
            "configuracao": configuracao_do_agente(),
        },
        "ferramentas": {nome: versao_pacote(nome) for nome in FERRAMENTAS},
        "artefatos_congelados": {
            str(arquivo.relative_to(raiz)).replace("\\", "/"): hash_arquivo(arquivo)
            for padrao in PADROES
            for arquivo in sorted(raiz.glob(padrao))
            if arquivo.is_file() and arquivo.suffix != ".pyc"
        },
        "git": {
            "commit": comando("git", "-C", str(raiz), "rev-parse", "HEAD"),
            "tag": comando("git", "-C", str(raiz), "describe", "--tags", "--exact-match"),
        },
        "suites": {},
    }
    for nome in ["base", "propriedades", "e1", "e2"]:
        total = sum(arquivo.read_text(encoding="utf-8").count("\ndef test_")
                    for arquivo in (raiz / "oracle" / nome).glob("test_*.py"))
        manifesto["suites"][nome] = {"testes_declarados": total}

    destino = raiz / "manifesto-experimento.json"
    destino.write_text(json.dumps(manifesto, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifesto, indent=2, ensure_ascii=False))
    print(f"\nGravado em {destino}")


if __name__ == "__main__":
    main()
