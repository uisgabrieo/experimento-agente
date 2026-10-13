# TCC - instrumento v2 e coleta 2

Infraestrutura experimental do TCC "Qualidade interna, preservação de
invariantes e capacidade de absorção de mudanças em aplicação gerada por agente
de inteligência artificial".

Comece por `LEIA-PRIMEIRO.txt`: ele traz, na ordem, o que fazer com a coleta 1
(reavaliação, sem gastar cota) e como conduzir a coleta 2.

Documentos de método:

- `metodologia/auditoria-instrumento-v2.md`: causa do defeito do RF34, auditoria
  dos 80 testes, do oráculo, do medidor e do orquestrador, e validação da
  versão 2 (estados reais, variantes aderentes e mutantes);
- `metodologia/protocolo-execucao.md`: protocolo da coleta 2, inclusive a regra
  de decisão entre as coletas;
- `artefatos/`: especificação v2, requisitos de mudança E1 e E2.

Desenho, em resumo: cada repetição gera a aplicação a partir da especificação
(M0), passa por cinco ciclos fixos de autocorreção alimentados por relatórios
externos (M1 a M5) e incorpora duas mudanças (E1, localizada; E2, transversal),
com até cinco tentativas cada. Suíte externa (55, 64 e 80 testes), oráculo de
oito invariantes por leitura do banco, Pylint, Radon, Bandit e cobertura medem
cada estado. O agente não executa código (`acceptEdits`) e não vê o
instrumento.
