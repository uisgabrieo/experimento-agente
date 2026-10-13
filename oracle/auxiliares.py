"""Concentra os recursos que aparecem em diferentes partes da suíte.

Eles ficam fora de `conftest.py` porque importar esse arquivo diretamente não é
uma prática recomendada pelo pytest e pode interferir na coleta.
"""
import os
import tempfile
import uuid
from datetime import datetime, timedelta

# A URL precisa existir antes que `conftest.py` importe a aplicação. Durante o
# experimento, o medidor envia `DATABASE_URL` e `SUITE_TCC=1` ao pytest e
# aponta o oráculo para esse mesmo arquivo.
#
# Sem essa coordenação, a suíte usaria o banco temporário criado aqui e o
# oráculo, em outro processo, abriria o caminho padrão. A avaliação recairia
# sobre bancos diferentes e não representaria o estado exercitado pelos testes.
#
# Na execução manual, fora do medidor, um banco temporário é suficiente.
if os.environ.get("SUITE_TCC") != "1":
    _BANCO = os.path.join(tempfile.gettempdir(), f"escala_{uuid.uuid4().hex}.db")
    os.environ["DATABASE_URL"] = f"sqlite:///{_BANCO}"
    os.environ["SUITE_TCC"] = "1"
for _chave in ("CHAVE_COORDENADOR", "CHAVE_PROFISSIONAL"):
    os.environ.pop(_chave, None)

from oracle.invariantes import verificar

# Os cenários usam esta segunda-feira como ponto comum de referência.
BASE = datetime(2026, 9, 7, 0, 0, 0)


# Violações já presentes no banco quando o cenário começou. Todos os cenários
# compartilham o mesmo banco; sem esta linha de base, uma violação produzida
# por um cenário reprovaria também todos os seguintes, que nada fizeram de
# errado. A versão 1 não separava as duas situações. A verificação global do
# estado continua sendo feita pelo medidor, ao final da suíte.
_LINHA_DE_BASE: set = set()


def registrar_linha_de_base():
    """Guarde as violações existentes antes do cenário (fixture automática)."""
    global _LINHA_DE_BASE
    _LINHA_DE_BASE = set(verificar().get("assinaturas", []))


def checar_invariantes():
    """Confirme que o cenário não introduziu violação de invariante no banco."""
    resultado = verificar()
    novas = sorted(set(resultado.get("assinaturas", [])) - _LINHA_DE_BASE)
    assert not novas, f"invariantes violadas pelo cenario: {novas[:20]}"


def email_unico():
    """Gere um endereço de e-mail exclusivo para o cenário em execução."""
    return f"p_{uuid.uuid4().hex[:12]}@exemplo.com"


def momento(dia=0, hora=8):
    """Monte um instante ISO a partir da data de referência da suíte."""
    return (BASE + timedelta(days=dia, hours=hora)).isoformat()


def numero(valor) -> float:
    """Converta para `float` um valor numérico recebido como número ou texto.

    A especificação não fixa a representação JSON de valores decimais. O
    Pydantic v2, por exemplo, serializa `Decimal` como texto (`"10.0"`).
    Comparar numericamente evita reprovar uma representação que a
    especificação admite.
    """
    return float(valor)
