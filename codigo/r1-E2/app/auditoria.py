"""Registro de auditoria das operacoes de escrita.

Toda requisicao a uma operacao de escrita (``POST``, ``PUT``, ``PATCH`` ou
``DELETE``) gera uma linha na tabela ``auditoria``, tanto em caso de
sucesso quanto quando a resposta e 4xx. As consultas da propria auditoria
nao geram registro.

O instante segue as convencoes de data e hora da especificacao: UTC,
apresentado em ISO 8601 pelos esquemas Pydantic.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Final, Sequence

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import count

from .banco import SESSAO_LOCAL
from .modelos import Auditoria
from .seguranca import CABECALHO_CHAVE, perfil_para_auditoria

#: Metodos considerados operacoes de escrita.
METODOS_DE_ESCRITA: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Prefixo das rotas da propria auditoria, excluidas do registro.
PREFIXO_AUDITORIA: Final = "/auditoria"


def _e_operacao_registravel(metodo: str, caminho: str) -> bool:
    """Indica se a requisicao deve gerar registro de auditoria."""

    if metodo not in METODOS_DE_ESCRITA:
        return False
    return not (
        caminho == PREFIXO_AUDITORIA or caminho.startswith(f"{PREFIXO_AUDITORIA}/")
    )


def registrar(metodo: str, caminho: str, perfil: str, codigo_resposta: int) -> None:
    """Grava uma linha na tabela ``auditoria``, em sessao propria."""

    sessao = SESSAO_LOCAL()
    try:
        sessao.add(
            Auditoria(
                metodo=metodo,
                caminho=caminho,
                perfil=perfil,
                codigo_resposta=codigo_resposta,
            )
        )
        sessao.commit()
    finally:
        sessao.close()


async def intermediario_de_auditoria(
    requisicao: Request,
    proxima: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Intermediario HTTP que audita as operacoes de escrita.

    Fica na borda da aplicacao para observar o codigo final da resposta,
    inclusive os ``401``, ``403``, ``409`` e ``422`` produzidos pelas
    dependencias de autenticacao e pelas regras de negocio.
    """

    resposta = await proxima(requisicao)

    metodo = requisicao.method.upper()
    caminho = requisicao.url.path
    if _e_operacao_registravel(metodo, caminho):
        registrar(
            metodo,
            caminho,
            perfil_para_auditoria(requisicao.headers.get(CABECALHO_CHAVE)),
            resposta.status_code,
        )
    return resposta


def listar(
    sessao: Session, limite: int, deslocamento: int
) -> tuple[Sequence[Auditoria], int]:
    """Pagina de registros de auditoria e o total existente."""

    total = sessao.scalar(select(count()).select_from(Auditoria)) or 0
    itens = sessao.scalars(
        select(Auditoria).order_by(Auditoria.id).offset(deslocamento).limit(limite)
    ).all()
    return itens, int(total)
