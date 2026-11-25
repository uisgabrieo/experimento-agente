"""Dependencias compartilhadas pelos roteadores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..db import obter_sessao
from ..tempo import para_utc_naive

Sessao = Annotated[Session, Depends(obter_sessao)]

LIMITE_PADRAO = 20
LIMITE_MAXIMO = 100


@dataclass(frozen=True)
class Paginacao:
    """Parametros ``limite``/``deslocamento`` das listagens (RF04)."""

    limite: int
    deslocamento: int


def paginacao(
    limite: int = Query(LIMITE_PADRAO, ge=1, le=LIMITE_MAXIMO),
    deslocamento: int = Query(0, ge=0),
) -> Paginacao:
    """Dependencia que resolve os parametros de paginacao."""

    return Paginacao(limite=limite, deslocamento=deslocamento)


Pag = Annotated[Paginacao, Depends(paginacao)]


@dataclass(frozen=True)
class Periodo:
    """Filtros temporais ``de``/``ate`` da secao 4.4, normalizados em UTC."""

    de: datetime | None
    ate: datetime | None


def periodo(
    de: datetime | None = Query(
        None, description="limite inicial inclusivo, ISO 8601 em UTC"
    ),
    ate: datetime | None = Query(
        None, description="limite final exclusivo, ISO 8601 em UTC"
    ),
) -> Periodo:
    """Dependencia que normaliza os filtros temporais em UTC *naive*."""

    return Periodo(
        de=para_utc_naive(de) if de is not None else None,
        ate=para_utc_naive(ate) if ate is not None else None,
    )


Intervalo = Annotated[Periodo, Depends(periodo)]


def paginar(sessao: Session, base: Select, pag: Paginacao, *ordem) -> dict:
    """Monta o envelope ``{itens, total}`` aplicando a paginacao.

    ``total`` sempre reflete a consulta inteira, nao a pagina devolvida.
    """

    # pylint: disable-next=not-callable  (func.count e construida dinamicamente)
    total = sessao.scalar(select(func.count()).select_from(base.subquery())) or 0
    itens = (
        sessao.scalars(
            base.order_by(*ordem).offset(pag.deslocamento).limit(pag.limite)
        )
        .unique()
        .all()
    )
    return {"itens": list(itens), "total": int(total)}


def validar_opcao(valor: str | None, permitidos: tuple[str, ...], campo: str) -> str | None:
    """Valida um filtro de enumeracao; valores fora do dominio dao 422."""

    if valor is not None and valor not in permitidos:
        raise ValueError(
            f"{campo} invalido: '{valor}' (esperado um de {', '.join(permitidos)})"
        )
    return valor
