"""Camada de persistencia: engine, sessao e base declarativa."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from importlib import import_module

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import e_sqlite, url_banco


class Base(DeclarativeBase):  # pylint: disable=too-few-public-methods
    """Base declarativa compartilhada por todos os modelos."""


def _criar_engine() -> Engine:
    """Cria o engine do SQLAlchemy conforme a URL configurada."""

    url = url_banco()
    opcoes: dict[str, object] = {"future": True, "pool_pre_ping": True}
    if e_sqlite(url):
        # ``check_same_thread`` precisa ser desligado porque o FastAPI pode
        # atender requisicoes em threads distintas do pool.
        opcoes["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **opcoes)  # type: ignore[arg-type]


engine: Engine = _criar_engine()

#: Fabrica de sessoes usada pela dependencia :func:`obter_sessao`. O nome segue
#: a convencao do SQLAlchemy, por isso a excecao a regra de nomes constantes.
SessionLocal = sessionmaker(  # pylint: disable=invalid-name
    bind=engine, autoflush=False, expire_on_commit=False, future=True
)


@event.listens_for(Engine, "connect")
def _ativar_chaves_estrangeiras(conexao, _registro) -> None:  # pragma: no cover - infra
    """Garante integridade referencial no SQLite.

    O PRAGMA so existe no SQLite; em outros bancos a verificacao de chaves
    estrangeiras ja e padrao e nada precisa ser feito.
    """

    if not isinstance(conexao, sqlite3.Connection):
        return
    cursor = conexao.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def criar_tabelas() -> None:
    """Cria o esquema no banco configurado, caso ainda nao exista."""

    # Importado em tempo de execucao para registrar os modelos no metadata
    # sem criar um ciclo de importacao com :mod:`app.models`.
    import_module("app.models")
    Base.metadata.create_all(bind=engine)


def obter_sessao() -> Iterator[Session]:
    """Dependencia do FastAPI que entrega uma sessao por requisicao.

    O ``commit`` e responsabilidade de cada rota: assim, qualquer excecao
    levantada no meio de uma operacao descarta as alteracoes parciais e
    preserva as invariantes do sistema.
    """

    sessao = SessionLocal()
    try:
        yield sessao
    except Exception:
        sessao.rollback()
        raise
    finally:
        sessao.close()
