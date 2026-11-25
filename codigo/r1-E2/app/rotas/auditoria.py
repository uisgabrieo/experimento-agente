"""Rota de consulta do registro de auditoria."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import auditoria as servico_auditoria
from .. import constantes as C
from ..banco import obter_sessao
from ..esquemas import AuditoriaResposta, Pagina
from ..seguranca import exigir_coordenador

roteador = APIRouter(prefix="/auditoria", tags=["auditoria"])


@roteador.get(
    "",
    response_model=Pagina[AuditoriaResposta],
    summary="Listar registros de auditoria",
    dependencies=[Depends(exigir_coordenador)],
)
def listar_auditoria(
    sessao: Session = Depends(obter_sessao),
    limite: int = Query(C.LIMITE_PADRAO, ge=1, le=C.LIMITE_MAXIMO),
    deslocamento: int = Query(C.DESLOCAMENTO_PADRAO, ge=0),
) -> dict[str, object]:
    """Listagem ``{itens, total}``, restrita ao perfil ``coordenador``.

    Com a autenticacao desativada a rota e acessivel sem ``X-Auth-Key``,
    como as demais.
    """

    itens, total = servico_auditoria.listar(sessao, limite, deslocamento)
    return {"itens": list(itens), "total": total}
