#!/usr/bin/env python3
"""Gera a matriz que relaciona os requisitos aos testes.

Uso:
    python rastreabilidade.py

O resultado é salvo em `metodologia/rastreabilidade.md` e pode ser incluído no
apêndice do trabalho. A matriz evidencia que os testes foram derivados da
especificação, e não o contrário.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).parent


def main():
    spec = (RAIZ / "artefatos" / "spec.md").read_text(encoding="utf-8")
    requisitos = sorted(set(re.findall(r"\*\*(RF\d{2})", spec)),
                        key=lambda r: int(r[2:]))
    invariantes = sorted(set(re.findall(r"\*\*(INV\d)\*\*", spec)))

    testes: dict[str, list[str]] = {}
    for arquivo in sorted((RAIZ / "oracle").rglob("test_*.py")):
        texto = arquivo.read_text(encoding="utf-8")
        for bloco in re.split(r"\ndef ", texto)[1:]:
            nome = bloco.split("(")[0]
            # Aqui entram apenas funções de teste. Funções auxiliares, como
            # `dados_profissional`, também citam requisitos e inflariam a matriz
            # se fossem interpretadas como evidência de cobertura.
            if not nome.startswith("test_"):
                continue
            corpo = bloco[:600]
            for requisito in requisitos:
                if re.search(rf"(rf{requisito[2:]}|{requisito})", corpo, re.I):
                    testes.setdefault(requisito, []).append(
                        f"{arquivo.parent.name}/{arquivo.stem}::{nome}")
            for invariante in invariantes:
                if re.search(rf"({invariante}|inv{invariante[3:]})", corpo, re.I):
                    testes.setdefault(invariante, []).append(
                        f"{arquivo.parent.name}/{arquivo.stem}::{nome}")

    validacao = (RAIZ / "validacao_oraculo" / "test_oraculo.py")
    texto_val = validacao.read_text(encoding="utf-8") if validacao.exists() else ""

    linhas = ["# Matriz de rastreabilidade", "",
              "Gerada por `rastreabilidade.py` a partir da especificação e das suítes.",
              "",
              "> **Alcance desta matriz.** A associação é feita por menção ao",
              "> identificador do requisito no nome ou no corpo do teste. Ela",
              "> demonstra **rastreabilidade** — que existe ao menos um teste",
              "> referente a cada requisito — e não cobertura integral do",
              "> comportamento especificado. Um requisito com múltiplas condições",
              "> pode constar como rastreado ainda que apenas parte delas seja",
              "> exercitada.",
              "", "## Requisitos funcionais", "",
              "| Requisito | Testes | Situação |", "|---|---|---|"]
    descobertos = 0
    for requisito in requisitos:
        lista = testes.get(requisito, [])
        if lista:
            descobertos += 1
        linhas.append(f"| {requisito} | {len(lista)} | "
                      f"{'rastreado' if lista else '**SEM RASTREABILIDADE**'} |")

    linhas += ["", f"**{descobertos} de {len(requisitos)} requisitos rastreados.**",
               "", "## Invariantes", "",
               "| Invariante | Testes na suíte | Validação do oráculo |",
               "|---|---|---|"]
    for invariante in invariantes:
        n_suite = len(testes.get(invariante, []))
        n_val = len(re.findall(rf"inv{invariante[3:]}", texto_val, re.I))
        linhas.append(f"| {invariante} | {n_suite} | {n_val} |")

    linhas += ["", "## Detalhamento por requisito", ""]
    for requisito in requisitos:
        lista = testes.get(requisito, [])
        linhas.append(f"**{requisito}**")
        for teste in sorted(set(lista)) or ["_sem teste_"]:
            linhas.append(f"- `{teste}`")
        linhas.append("")

    destino = RAIZ / "metodologia" / "rastreabilidade.md"
    destino.write_text("\n".join(linhas), encoding="utf-8")
    print(f"{descobertos}/{len(requisitos)} requisitos rastreados")
    print(f"Gravado em {destino}")


if __name__ == "__main__":
    main()
