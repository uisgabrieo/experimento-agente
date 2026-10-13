"""Conta as repetições completas da coleta 2, pela regra do protocolo.

Repetição completa: os oito estados (M0 a M5, E1 e E2) medidos, todos com
instrumentos_validos = sim. Uma aplicação que não importa (app_importa = nao)
continua valendo como resultado do agente.

Uso, na pasta tcc-v2:
    python contar_completas.py
    python contar_completas.py --saida <pasta com resultados.csv>
"""

import argparse
import csv
from pathlib import Path

ESTADOS = ["M0", "M1", "M2", "M3", "M4", "M5", "E1", "E2"]


def main() -> None:
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--saida", default=str(Path(__file__).resolve().parent / "coleta"))
    arquivo = Path(analisador.parse_args().saida) / "resultados.csv"
    if not arquivo.exists():
        print(f"{arquivo} ainda nao existe: nenhuma repeticao medida.")
        print("Repeticoes completas: 0")
        return
    with open(arquivo, encoding="utf-8", newline="") as entrada:
        linhas = list(csv.DictReader(entrada))
    por_repeticao: dict[str, dict[str, dict]] = {}
    for linha in linhas:
        por_repeticao.setdefault(linha["app"], {})[linha["estado"]] = linha
    completas = 0
    for app in sorted(por_repeticao, key=lambda nome: int(nome[1:])):
        estados = por_repeticao[app]
        faltam = [estado for estado in ESTADOS if estado not in estados]
        invalidos = [estado for estado in ESTADOS
                     if estado in estados and estados[estado]["instrumentos_validos"] != "sim"]
        if not faltam and not invalidos:
            completas += 1
            situacao = "COMPLETA"
        else:
            partes = []
            if faltam:
                partes.append("faltam " + " ".join(faltam))
            if invalidos:
                partes.append("instrumento invalido em " + " ".join(invalidos))
            situacao = "; ".join(partes)
        print(f"{app}: {situacao}")
    print(f"Repeticoes completas: {completas}")


if __name__ == "__main__":
    main()
