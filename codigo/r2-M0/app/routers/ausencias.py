"""RF35 - registro de ausencias."""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from ..erros import nao_encontrado
from ..estados import TIPOS_AUSENCIA
from ..models import Ausencia
from ..schemas import AusenciaCriar, AusenciaSaida, Pagina
from ..servicos import obter_profissional, registrar_ausencia
from .comum import Intervalo, Pag, Sessao, paginar, validar_opcao

router = APIRouter(prefix="/ausencias", tags=["ausencias"])


@router.post(
    "",
    response_model=AusenciaSaida,
    status_code=status.HTTP_201_CREATED,
    summary="RF35 - registrar ausencia",
)
def criar_ausencia(dados: AusenciaCriar, sessao: Sessao) -> Ausencia:
    profissional = obter_profissional(sessao, dados.profissional_id)
    ausencia = registrar_ausencia(
        sessao, profissional, dados.data_inicio, dados.data_fim, dados.tipo
    )
    sessao.commit()
    return ausencia


@router.get("", response_model=Pagina[AusenciaSaida], summary="Listar ausencias")
def listar_ausencias(
    sessao: Sessao,
    pag: Pag,
    intervalo: Intervalo,
    profissional_id: int | None = Query(None, ge=1),
    tipo: str | None = Query(None),
) -> dict:
    base = select(Ausencia)
    if profissional_id is not None:
        base = base.where(Ausencia.profissional_id == profissional_id)
    if validar_opcao(tipo, TIPOS_AUSENCIA, "tipo") is not None:
        base = base.where(Ausencia.tipo == tipo)
    # Mesma convencao da secao 4.4 aplicada ao intervalo da ausencia.
    if intervalo.de is not None:
        base = base.where(Ausencia.data_fim > intervalo.de)
    if intervalo.ate is not None:
        base = base.where(Ausencia.data_inicio < intervalo.ate)
    return paginar(sessao, base, pag, Ausencia.data_inicio, Ausencia.id)


@router.get(
    "/{ausencia_id}", response_model=AusenciaSaida, summary="Consultar ausencia"
)
def consultar_ausencia(ausencia_id: int, sessao: Sessao) -> Ausencia:
    ausencia = sessao.get(Ausencia, ausencia_id)
    if ausencia is None:
        raise nao_encontrado("ausencia", ausencia_id)
    return ausencia
