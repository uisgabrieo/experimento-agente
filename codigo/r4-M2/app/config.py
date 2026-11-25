"""Configuracao da aplicacao.

Toda a configuracao e lida de variaveis de ambiente, com valores padrao
adequados para execucao local com SQLite.
"""

from __future__ import annotations

import os

#: URL de conexao do banco de dados.
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./escala.db")

#: Titulo exposto na documentacao automatica.
TITULO_API: str = "Sistema de Escala de Plantao"

#: Versao do contrato funcional implementado.
VERSAO_API: str = "1.0.0"


def url_banco() -> str:
    """Retorna a URL do banco, relendo o ambiente a cada chamada.

    Reler o ambiente permite que testes apontem ``DATABASE_URL`` para um
    arquivo temporario antes de importar o modulo de banco.
    """

    return os.getenv("DATABASE_URL", DATABASE_URL)


def e_sqlite(url: str | None = None) -> bool:
    """Indica se a URL informada aponta para um banco SQLite."""

    return (url or url_banco()).startswith("sqlite")
