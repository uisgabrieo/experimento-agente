"""Configuracao da aplicacao.

A unica configuracao externa prevista na especificacao e a variavel de
ambiente ``DATABASE_URL``, cujo valor padrao e ``sqlite:///./escala.db``.
"""

from __future__ import annotations

import os

DATABASE_URL_PADRAO = "sqlite:///./escala.db"

TITULO = "Sistema de Escala de Plantao"
DESCRICAO = (
    "API para montagem e manutencao da escala mensal de plantoes de uma "
    "clinica de medio porte. Todas as datas e horarios sao tratados em UTC "
    "e representados em ISO 8601."
)


def obter_database_url() -> str:
    """Retorna a URL do banco de dados em uso.

    A leitura e feita a cada chamada para que a variavel de ambiente possa
    ser ajustada por testes antes da criacao do engine.
    """

    url = os.getenv("DATABASE_URL")
    if url is None or not url.strip():
        return DATABASE_URL_PADRAO
    return url.strip()
