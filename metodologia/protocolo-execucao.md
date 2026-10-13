# Protocolo de execução — coleta 2 (instrumento v2)

Documento congelado com os demais artefatos, antes da primeira execução da
coleta 2. Substitui o protocolo da coleta 1 no que for diferente; o restante
permanece.

---

## 1. Por que existe uma coleta 2

Na coleta 1, três testes da suíte base exigiam comportamentos que a
especificação não determina (RF33, RF34 e RF36; ver
`metodologia/auditoria-instrumento-v2.md`). O teste do RF34 reprovou todas as
aplicações que carregavam, e o relatório devolvido ao agente o apontou como
falha em todos os ciclos. A auditoria completa dos 80 testes encontrou outros
pontos do mesmo tipo, sem efeito nos dados da coleta 1, e defeitos de medição
e de orquestração. Conforme a seção 5 do protocolo da coleta 1, a alteração de
testes exige nova versão congelada; a coleta 2 é essa versão.

A coleta 1 é preservada integralmente (pasta `tcc`, etiquetas Git e
`C:\execucoes`) e reavaliada com o instrumento v2 por `reavaliar_v1.py`.

## 2. Regra de decisão, registrada antes da coleta 2

Data de corte: **07/11/2026, 23h59**.

- Se até a data de corte houver **pelo menos 5 repetições completas** da
  coleta 2, os resultados do TCC são os da coleta 2. A coleta 1 passa a ser
  descrita como coleta inicial cujos defeitos motivaram o instrumento v2.
- Caso contrário, os resultados do TCC são os da coleta 1, reavaliada com o
  instrumento v2. As repetições da coleta 2 concluídas até a data de corte
  são relatadas em apêndice, sem serem somadas à coleta 1.

Repetição completa: os oito estados (M0 a M5, E1, E2) congelados e medidos com
`instrumentos_validos = sim`. Uma aplicação que não importa é resultado do
agente e não torna a medição inválida (`app_importa = nao`).

As duas coletas nunca são combinadas na mesma análise: instrumento,
especificação e instruções diferem.

## 3. Política de repetição de execuções

Uma invocação do agente que falha (limite do plano, rede, tempo limite) não é
resultado: as edições parciais são descartadas, a repetição é interrompida e a
mesma invocação é refeita na retomada, com
`python orquestrador.py --continuar --inicio N --repeticoes K`. O mesmo vale
para uma tentativa de E1 ou E2 interrompida entre o seu commit e o registro do
progresso, e para edições encontradas na área ao retomar. Duas execuções
simultâneas sobre a mesma pasta de saída são recusadas.

Não são motivo para refazer uma repetição: aplicação que não inicializa,
testes reprovados, invariantes violadas, ausência de melhoria entre ciclos,
teto de tentativas atingido em E1 ou E2, ou variabilidade em relação às demais
repetições.

Nenhuma área de trabalho, CSV ou log é apagado. Uma repetição descartada por
defeito comprovado de instrumento é registrada em `coleta/ocorrencias.md`, com
data e motivo, e não é reaproveitada.

## 4. Condições fixas

- Agente: Claude Code na versão registrada no manifesto, atualização
  automática desativada, `--model opus`, `--permission-mode acceptEdits`.
  O orquestrador recusa iniciar se a versão mudar.
- Esforço (`effortLevel`) e demais opções de `~/.claude/settings.json`:
  registrados no manifesto e não alterados durante a coleta.
- Ferramentas de medição (pytest, hypothesis, coverage, pylint, radon, bandit
  e bibliotecas da aplicação): versões registradas no manifesto; o
  orquestrador recusa iniciar se alguma faltar ou mudar.
- Uma resposta do agente que seja apenas o aviso de limite de uso é tratada
  como falha da invocação, mesmo com código de saída 0.
- Ciclos: 5 ciclos fixos de autocorreção; E1 e E2 com até 5 tentativas cada,
  contadas entre retomadas.
- Contagens de testes: base 54, propriedades 1, E1 9, E2 16 (55, 64 e 80
  por grupo de estados).
- Áreas de trabalho em `C:\execucoes-v2`, com nomes e etiquetas derivados de
  sal diferente do da coleta 1.

## 5. O que muda em relação à coleta 1

Instrumento (todas as mudanças aplicadas também à reavaliação da coleta 1):

1. Suíte auditada: cada asserção decorre de cláusula da especificação; efeitos
   persistidos são lidos no banco pelo esquema obrigatório; formatos não fixados
   pela especificação são aceitos nas variantes possíveis.
2. Oráculo: INV2 verificada entre cada plantão e o seguinte, e não só entre
   vizinhos por início; datas com fuso convertidas para UTC.
3. Cada teste responde apenas pelas violações de invariante que introduz.
4. Medição: configuração das ferramentas fixada pelo instrumento; supressões
   inline contadas; Bandit restrito a `app/`; coleta válida só com o número
   exato de testes; aplicação que não importa registrada como resultado.

Orquestração:

5. A instrução de E2 traz o texto de E1, que continua em vigor.
6. O relatório de ciclo chama de "reprovados" os testes que falham, e mostra o
   erro de importação quando a suíte não pode ser executada.
7. Tentativas de E1 e E2 persistidas entre retomadas; registros gravados no
   momento do evento; logs nunca sobrescritos.
8. Toda medição e todo relatório operam sobre cópia do commit, fora da área do
   agente.

Especificação (alterações declaradas):

9. Linguagem: "Python 3.13" (a coleta 1 trazia uma nota do pesquisador).
10. Fora de escopo: "autenticação" (a coleta 1 antecipava a evolução futura).
11. RF06: o corpo recebe `especialidade_id`.
12. Cadastros por `POST` retornam o registro criado, com `id`.

## 6. Validade de uma medição

Uma medição é válida quando, cumulativamente:

- a suíte foi coletada com o número exato de testes, ou a aplicação não
  importa (`app_importa = nao`);
- o relatório JUnit foi produzido na própria execução;
- o oráculo avaliou o mesmo banco exercitado pela suíte, salvo quando a
  aplicação não importa;
- Pylint, Radon e Bandit produziram saída interpretável.

## 7. Modo simulado e piloto

O modo simulado usa agente substituto, grava em `simulacao/<data-hora>/` e em
pasta temporária, e nunca se mistura à coleta. A verificação do agente
(`--verificar-agente`) faz uma única chamada mínima e não produz dados.

## 8. Plano de análise

Mantido da coleta 1 (H1 a H4), com dois acréscimos:

- para o Pylint, reportar as ocorrências visíveis e as suprimidas por
  comentário, separadamente;
- reportar se o agente criou arquivos de configuração de ferramentas
  (`pylint_config_agente`), ainda que eles não afetem a medição.

O custo de absorção de E1 e E2 é a quantidade de tentativas até o critério,
além de arquivos e linhas alterados em `app/` (colunas `arquivos_tocados` e
`linhas_*` de `coleta/evolucoes.csv`; as colunas `*_total` incluem os arquivos
que o agente cria fora de `app/`, como roteiros de verificação). Tokens e custo por invocação ficam em
`coleta/interacoes.csv`.
