"""Configuracao da aplicacao.

Toda a configuracao vem de variaveis de ambiente, com valores padrao
compativeis com a execucao local.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DATABASE_URL_PADRAO = "sqlite:///./escala.db"


@dataclass(frozen=True)
class Configuracao:
    """Valores de configuracao resolvidos no momento da importacao."""

    database_url: str
    echo_sql: bool

    @property
    def e_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def e_sqlite_memoria(self) -> bool:
        return self.e_sqlite and (
            ":memory:" in self.database_url or self.database_url.endswith("sqlite://")
        )


def carregar_configuracao() -> Configuracao:
    """Le as variaveis de ambiente e devolve a configuracao efetiva."""

    echo = (os.getenv("SQL_ECHO") or "").strip().lower() in {"1", "true", "yes", "on"}
    return Configuracao(
        database_url=os.getenv("DATABASE_URL") or DATABASE_URL_PADRAO, echo_sql=echo
    )


config = carregar_configuracao()
