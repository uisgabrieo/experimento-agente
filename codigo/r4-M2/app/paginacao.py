"""Paginacao compartilhada pelas rotas de listagem.

Todas as listagens da API respondem no envelope ``{itens, total}`` com os
parametros ``limite`` e ``deslocamento``. Concentrar a montagem da consulta
aqui evita repetir o mesmo bloco em cada rota.
"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def paginar(
    sessao: Session,
    consulta: Select,
    *,
    limite: int = 20,
    deslocamento: int = 0,
) -> dict[str, object]:
    """Executa ``consulta`` recortada pela pagina e devolve ``{itens, total}``.

    ``total`` conta todas as linhas que a consulta retornaria, ignorando o
    recorte: e o tamanho do conjunto filtrado, nao o da pagina.
    """

    # pylint: disable-next=not-callable
    contagem = select(func.count()).select_from(consulta.order_by(None).subquery())
    total = int(sessao.execute(contagem).scalar_one() or 0)
    pagina = consulta.offset(deslocamento).limit(limite)
    itens = sessao.execute(pagina).scalars().all()
    return {"itens": list(itens), "total": total}
