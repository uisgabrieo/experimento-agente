"""Camada de persistencia: engine, sessao e classe base declarativa.

Persistencia em SQLite via SQLAlchemy 2.x. A URL de conexao vem da
variavel de ambiente ``DATABASE_URL`` (padrao ``sqlite:///./escala.db``).
"""

from __future__ import annotations

from contextlib import suppress
from sqlite3 import Error as ErroSQLite
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import obter_database_url


class Base(DeclarativeBase):  # pylint: disable=too-few-public-methods
    """Classe base de todos os modelos mapeados."""


def _argumentos_de_conexao(url: str) -> dict[str, object]:
    """Argumentos extras necessarios para drivers SQLite."""

    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


DATABASE_URL = obter_database_url()

engine: Engine = create_engine(
    DATABASE_URL,
    connect_args=_argumentos_de_conexao(DATABASE_URL),
    future=True,
)

SESSAO_LOCAL = sessionmaker(
    bind=engine,
    autoflush=True,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


@event.listens_for(Engine, "connect")
def _ativar_chaves_estrangeiras(conexao, _registro) -> None:  # pragma: no cover
    """Habilita a verificacao de chaves estrangeiras no SQLite."""

    if not DATABASE_URL.startswith("sqlite"):
        return
    # Drivers que nao suportam o PRAGMA simplesmente o ignoram.
    with suppress(ErroSQLite, AttributeError):
        cursor = conexao.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def obter_sessao() -> Iterator[Session]:
    """Dependencia FastAPI que fornece uma sessao por requisicao."""

    sessao = SESSAO_LOCAL()
    try:
        yield sessao
    finally:
        sessao.close()
