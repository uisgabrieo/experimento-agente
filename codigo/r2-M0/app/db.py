"""Infraestrutura de persistencia (SQLAlchemy 2.x sobre SQLite)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import config


class Base(DeclarativeBase):
    """Classe base declarativa de todos os modelos."""


def _argumentos_do_engine() -> dict[str, Any]:
    kwargs: dict[str, Any] = {"echo": config.echo_sql, "future": True}
    if config.e_sqlite:
        # O FastAPI atende requisicoes em threads distintas; a sessao e
        # criada e descartada dentro de cada requisicao.
        kwargs["connect_args"] = {"check_same_thread": False}
        if config.e_sqlite_memoria:
            # Mantem um unico banco em memoria para todo o processo.
            kwargs["poolclass"] = StaticPool
    return kwargs


engine: Engine = create_engine(config.database_url, **_argumentos_do_engine())

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


if config.e_sqlite:

    @event.listens_for(engine, "connect")
    def _configurar_sqlite(dbapi_connection, _registro) -> None:  # pragma: no cover
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def criar_esquema() -> None:
    """Cria as tabelas descritas na secao 2.1, se ainda nao existirem."""

    from . import models  # noqa: F401  (registra os modelos no metadata)

    Base.metadata.create_all(bind=engine)


def obter_sessao() -> Iterator[Session]:
    """Dependencia do FastAPI: uma sessao por requisicao."""

    sessao = SessionLocal()
    try:
        yield sessao
    finally:
        sessao.close()
