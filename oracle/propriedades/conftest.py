"""
Ponte de fixtures.

O pytest carrega `conftest.py` apenas de diretórios acima do alvo da coleta,
segundo o `rootdir` determinado na invocação. Quando as suítes de aceitação são
executadas isoladamente — `pytest oracle/e1` —, o `conftest.py` de `oracle/`
pode não ser alcançado, e as fixtures ficam indisponíveis.

O sintoma é `failed on setup`: os testes não chegam a executar, e o relatório
registra falhas que não correspondem ao comportamento do artefato avaliado.

Reexportar as fixtures aqui torna a suíte independente do diretório a partir do
qual é invocada.
"""

from oracle.conftest import (  # noqa: F401
    alocar,
    cliente,
    criar_especialidade,
    criar_profissional,
    criar_turno,
    linha_de_base_das_invariantes,
)
