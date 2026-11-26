# Auditoria do instrumento e versão 2

Auditoria concluída em 12/10/2026 sobre o pacote congelado da coleta 1
(etiqueta `EXPERIMENTO-V1-CONGELADO`, commit `54910fc`), os commits
preservados em `C:\execucoes` e os textos `spec.md`, `evolucao-e1.md` e
`evolucao-e2.md`. Nenhuma chamada ao agente foi feita e nenhum dado da coleta 1
foi alterado.

## 1. Resumo

- **Causa do erro.** Os testes dos requisitos RF33, RF34 e RF36 exigiam
  comportamentos que a especificação não determina; o do RF34 exigia,
  inclusive, que a rota do RF36 violasse o próprio RF36. Eles foram calibrados
  contra uma única implementação de referência, que, para aprová-los,
  precisava ter os mesmos desvios.
- **Auditoria completa.** Dos 80 testes, 13 exigiam algo que a
  especificação não determina e podiam reprovar uma implementação correta; 21
  dependiam de premissas não declaradas sobre o corpo das respostas; 1 passava
  sem verificar o que afirmava (RF22); 6 verificavam só parte do que
  afirmavam; 39 estavam corretos. O oráculo tinha três defeitos, sem efeito
  nos dados. A medição aceitava configuração deixada pelo agente.
- **Validação da versão 2.** Nos estados da coleta 1 em que a aplicação
  carrega, a suíte v2 e a suíte corrigida de 06/10 concordam em todos os
  testes comuns; em relação à v1, os testes comuns só diferem no do RF34 e
  nos do RF33 e do RF36 (os estados em que a fila era uma lista).
  Em 11 variantes que cumprem a especificação, a suíte v2 não reprova nenhuma
  (a de 06/10 reprovava 7; a v1, 8). Em 23 mutantes que violam uma cláusula,
  a suíte v2 detecta os 23 (a de 06/10, 15; a v1, 13).
- **Achado novo sobre os dados.** Parte da queda das ocorrências do Pylint
  entre M0 e M5 veio de supressão, não de correção: comentários
  `# pylint: disable` em todas as repetições e, em r2, um `.pylintrc` criado
  pelo agente. A medição v2 fixa a configuração e conta as supressões.

## 2. O defeito que motivou a auditoria

Arquivo `oracle/base/test_complementares.py`, função
`test_rf34_aceite_cria_plantao` (linhas 218 a 258 da versão 1), e
`oracle/base/test_substituicoes.py`, funções
`test_rf33_cancelamento_reordena_a_fila` (linha 106) e
`test_rf36_consultar_fila` (linha 126).

### 2.1 O que o teste do RF34 exigia, linha a linha

| Linha | Código da versão 1 | O que a especificação diz |
|---|---|---|
| 241–243 | realoca o mesmo profissional e, `if replantao.status_code == 201`, cancela de novo | se a realocação falhasse, o teste seguia em silêncio e falhava adiante com mensagem enganosa |
| 245 | `cliente.get(".../substituicoes").json()["itens"]` | RF36: "deve retornar 200 com a fila de substituições em estado `aguardando` ordenada por `posicao`". O envelope `{itens, total}` só é exigido em RF04, RF10, RF23 e RF29. |
| 246–249 | procura a inscrição nessa fila e exige `estado == "convocado"` | Pelo RF36, a rota só devolve inscrições em `aguardando`. Uma inscrição convocada **não pode** aparecer nela. |
| 253 | `resposta.json()["estado"] == "confirmado"` | RF34: "deve criar um plantão em estado `confirmado`, marcar a substituição como `atendida` e retornar 201". O corpo da resposta não é definido. |
| 255–257 | procura de novo na fila e exige `estado == "atendida"` | mesmo problema da linha 246: impossível pela rota do RF36 |

Nos testes do RF33 (linha 106) e do RF36 (linha 126), `.json()["itens"]` exigia
o envelope na rota do RF36.

### 2.2 Por que nenhuma implementação correta passava

O teste procurava a inscrição convocada na rota que, por especificação, só
devolve inscrições em espera. Uma implementação correta nunca a mostra ali.
Para passar, a aplicação precisava violar o RF36.

A comprovação está na seção 8: o mutante M05 (rota do RF36 devolvendo
inscrições em qualquer estado) faz o teste da versão 1 **passar**, enquanto a
implementação correta o faz falhar.

### 2.3 Por que o defeito não foi visto antes

Os testes foram calibrados contra uma implementação de referência escrita
durante a preparação do instrumento. Para que o teste do RF34 passasse nela,
essa referência precisava devolver, na rota do RF36, inscrições em outros
estados além de `aguardando`, dentro do envelope `{itens, total}`, e devolver
o plantão no aceite: exatamente os desvios que o teste exigia.

A falha de método foi validar contra uma implementação, e não contra as
cláusulas da especificação. A versão 2 é validada contra as cláusulas: cada
asserção tem origem declarada (seção 4), e a suíte é exercitada contra
variantes que cumprem a especificação e contra mutantes que a violam
(seção 8).

### 2.4 Efeito na coleta 1

- O teste do RF34 reprovou em todos os estados em que a aplicação carrega.
  Nos relatórios JUnit canônicos, por `TypeError` ao ler `["itens"]` (fila
  devolvida como lista) ou por "a inscricao deveria constar na fila" (fila
  em envelope, sem a inscrição convocada). A chamada de aceite nunca chegou
  a ser feita.
- O relatório de cada ciclo levava ao agente a lista de testes reprovados com
  o rótulo "Regressoes", embora o teste falhasse desde M0. Os relatórios de
  ciclo preservados nos logs citaram o RF34, com exceção dos de r5, cuja
  aplicação não importa.
- Os agentes alternaram o formato da rota do RF36 entre lista e envelope em
  r2, r3 e r4 para tentar satisfazer o teste. A oscilação de 52 para 54
  aprovados em r2 e r3 era essa alternância, não perda de comportamento.
- O dano é irreversível nos dados da coleta 1: reavaliar os commits corrige o
  que se sabe sobre cada estado, mas não reconstrói o código que o agente teria
  escrito sob relatório correto.

## 3. Regras usadas na auditoria

1. Cada asserção deve decorrer de uma cláusula da especificação, da E1 ou da
   E2, ou de premissa declarada (abaixo).
2. Corpo de resposta só é verificado onde a especificação o define: RF04,
   RF10, RF23, RF29, RF25 (`detail`), RF37, RF38 e `GET /auditoria`.
3. Efeitos persistidos (estado, posição, horas extras, data de decisão,
   registro de auditoria) são lidos no banco, pelo esquema obrigatório da
   seção 2.1 e pelas colunas fixadas na E2. É o mecanismo do oráculo.
4. Onde a especificação admite mais de uma forma (lista ou envelope no RF36;
   recusa ou redução de `limite` acima de 100; leitura das chaves da E2 na
   importação ou a cada requisição; código 400 ou 422 para `noturno`
   inválido), todas são aceitas.
5. Números são comparados numericamente: `Decimal` pode chegar como texto.
6. Cada teste confere as próprias precondições, para que a falha apareça
   atribuída ao requisito certo.
7. Cada teste responde só pelas violações de invariante que introduz; o
   estado do banco inteiro é avaliado ao final, pelo medidor.

Premissas declaradas da suíte (a especificação v2 torna as duas primeiras
explícitas):

- P1: os cadastros por `POST` devolvem o registro criado com o seu `id`;
- P2: o corpo do RF06 traz `especialidade_id`;
- P3: data e hora ISO 8601 sem fuso é interpretada como UTC;
- P4: o banco grava data e hora em texto ISO 8601, como faz o SQLAlchemy.

## 4. Resultado, teste por teste

Legenda da versão 1: **inválido** = podia reprovar implementação correta;
**premissa** = dependia de campo ou tipo de corpo não fixado; **trivial** =
passava sem verificar o que afirma; **parcial** = verificava só parte do que
afirma; **correto** = sem mudança de conteúdo.

### Suíte base (54)

| # | Teste | Cláusula | Versão 1 | Versão 2 |
|---|---|---|---|---|
| 1 | test_rf13_alocar_plantao | RF13 | premissa (`estado` no corpo) | estado lido no banco |
| 2 | test_rf14_sem_especialidade | RF14 | correto | — |
| 3 | test_rf15_sobreposicao | RF15 | correto | — |
| 4 | test_rf16_descanso_menor_que_11h | RF16 | correto | — |
| 5 | test_rf16_descanso_de_exatamente_11h_permitido | RF16, 4.1 | correto | — |
| 6 | test_rf17_excede_44_horas_semanais | RF17 | correto | — |
| 7 | test_rf18_sobreposicao_com_ausencia | RF18 | parcial (ausência não conferida) | confere o registro da ausência |
| 8 | test_rf19_setimo_dia_consecutivo | RF19 | correto | — |
| 9 | test_rf20_profissional_inativo | RF20 | correto | — |
| 10 | test_rf21_ja_alocado_no_mesmo_turno | RF21 | correto | — |
| 11 | test_rf22_cancelamento_libera_horas | RF22 | **trivial**: 12 h com carga de 20 h nunca geram hora extra | 2 × 12 h na semana (4 h extras); cancela; confere 200, `cancelado` e 0 h extras |
| 12 | test_rf01_criar_profissional | RF01, seção 3 | premissa (corpo e tipo de `horas_extras`) | banco |
| 13–17 | test_rf02_* (5 testes) | RF02 | correto | — |
| 18 | test_rf03_email_duplicado | RF03 | correto | — |
| 19 | test_rf04_listar_profissionais | RF04 | correto (exigia `total` inteiro) | `total` numérico |
| 20 | test_rf04_limite_acima_do_maximo_recusado → **test_rf04_limite_maximo_de_100** | RF04 | **inválido**: exigia 422 | recusa 4xx ou no máximo 100 itens, com mais de 100 cadastrados |
| 21 | test_rf05_consultar_profissional_inexistente | RF05, RF37 | correto | — |
| 22 | test_rf06_vinculo_duplicado | RF06 | parcial | vínculo conferido no banco |
| 23 | test_rf08_especialidade_duplicada | RF08 | correto | — |
| 24 | test_rf07_remover_especialidade_sem_plantao | RF07 | parcial (só o código) | vínculo removido no banco |
| 25 | test_rf07_remover_especialidade_com_plantao_confirmado | RF07 | correto | vínculo preservado no banco |
| 26 | test_rf12_excluir_turno_sem_plantao | RF11, RF12 | correto | — |
| 27 | test_rf12_excluir_turno_com_plantao_confirmado | RF12 | correto | turno preservado no banco |
| 28 | test_rf23_consultar_escala | RF23 | premissa (tipo de `horas_periodo`) | numérico |
| 29 | test_rf23_escala_respeita_o_periodo | RF23, 4.4 | premissa; precondições não conferidas | numérico; precondições |
| 30 | test_rf24_troca_entre_plantoes_do_mesmo_profissional | RF24 | precondições não conferidas | precondições |
| 31 | test_rf24_troca_com_plantao_cancelado | RF24 | precondições não conferidas | precondições; cancelamento conferido no banco |
| 32 | test_rf29_listar_trocas_com_filtro | RF29 | premissa (`estado` nos itens); parcial | ids conferidos contra o banco; uma troca rejeitada no cenário |
| 33 | test_rf28_cancelamento_rejeita_troca_automaticamente | RF28 | premissa; parcial (não conferia `data_decisao`, embora o dissesse) | banco: `rejeitada` e `data_decisao` |
| 34 | test_rf34_aceite_fora_do_estado_convocado | RF34 | premissa (`estado` no corpo) | banco; confere que nada muda |
| 35 | test_rf34_aceite_cria_plantao | RF34, RF22, RF36 | **inválido** (seção 2) | reescrito: banco; sem realocação |
| 36 | test_rf30_entrar_na_fila | RF30 | premissa | banco |
| 37 | test_rf30_segunda_inscricao_recebe_posicao_2 | RF30 | premissa | banco |
| 38 | test_rf31_cobertura_ja_atendida | RF31 | correto | — |
| 39 | test_rf32_sem_especialidade | RF32 | correto | — |
| 40 | test_rf33_cancelar_inscricao | RF33 | parcial (só o código) | estado `cancelada` no banco |
| 41 | test_rf33_cancelamento_reordena_a_fila | RF33, INV6 | **inválido** (envelope na rota do RF36) | posições no banco |
| 42 | test_rf36_consultar_fila | RF36 | **inválido** (envelope) | lista ou envelope; ids e ordem conferidos contra o banco, com uma inscrição cancelada |
| 43 | test_rf35_ausencia_com_plantao_sobreposto | RF35 | correto | — |
| 44 | test_rf37_erro_404_contem_detail | RF37 | correto | — |
| 45 | test_rf38_rota_de_saude | RF38 | correto | — |
| 46 | test_rf25_troca_valida_permuta_os_dois | RF25 | **inválido**: usava `GET /plantoes/{id}`, rota não especificada | banco; também `aprovada` e `data_decisao` |
| 47 | test_rf25_troca_invalida_nao_altera_nada | RF25 | premissa: comparava `GET /plantoes/{id}` antes e depois; sem essa rota, comparava duas respostas 404 e passava sem verificar nada | banco; precondições |
| 48 | test_rf27_decidir_troca_ja_decidida | RF26, RF27 | parcial (só códigos) | `rejeitada`, `data_decisao` e plantões intactos |
| 49 | test_rf09_criar_turno | RF09 | premissa (corpo) | banco |
| 50 | test_rf09_duracao_curta_recusada | RF09 | correto | — |
| 51 | test_rf09_duracao_longa_recusada | RF09 | correto | — |
| 52 | test_rf10_listar_turnos | RF10 | correto | `total` numérico |
| 53 | test_rf11_consultar_turno_inexistente | RF11, RF37 | correto | — |
| 54 | test_rf09_campos_exatos_do_turno → **test_rf09_duracoes_de_4h_e_12h_aceitas** | RF09, 2.1 | **inválido**: exigia conjunto exato de campos; a seção 2.1 admite colunas adicionais. Falhava por construção em E1 e E2 (era o único teste `MUDA`) | fronteiras de 4 h e 12 h |

### Suíte de propriedades (1)

| # | Teste | Cláusula | Versão 1 | Versão 2 |
|---|---|---|---|---|
| 55 | test_invariantes_sob_sequencia_arbitraria | seção 4 | correto | — |

### Suíte E1 (9)

| # | Teste | Versão 1 | Versão 2 |
|---|---|---|---|
| 56 | test_e1_criar_turno_noturno | premissa (`noturno` no corpo) | pelo filtro da própria E1, por id |
| 57 | test_e1_valor_padrao_e_false | premissa | pelo filtro, por id |
| 58 | test_e1_valor_invalido_recusado | **inválido**: exigia 422; a E1 não fixa o código | 400 ou 422, com `detail` |
| 59–61 | test_e1_filtro_* (3 testes) | premissa (`noturno` nos itens) | conjunto exato de ids devolvidos |
| 62 | test_e1_adicional_incide_no_total_do_periodo | premissa (tipo) | numérico; criação conferida |
| 63 | test_e1_adicional_nao_altera_horas_extras | premissa (corpo do RF05) | banco |
| 64 | test_e1_adicional_nao_altera_limite_semanal | correto | criação conferida |

### Suíte E2 (16)

| # | Teste | Versão 1 | Versão 2 |
|---|---|---|---|
| 65 | test_e2_sem_variaveis_comportamento_anterior | correto | — |
| 66 | test_e2_auditoria_acessivel_sem_chave_quando_desativada | correto (`total` inteiro) | `total` numérico |
| 67 | test_e2_perfil_registrado_como_desativada | frágil: `registros[-1]` supunha ordem e ausência de paginação | banco: um registro novo, perfil `desativada` |
| 68 | test_e2_sem_cabecalho_retorna_401 | **inválido** se a chave fosse lida na importação | instância da aplicação importada com as chaves |
| 69 | test_e2_chave_invalida_retorna_403 | **inválido** (idem) | idem |
| 70 | test_e2_chave_de_coordenador_permite_acesso | correto | idem |
| 71 | test_e2_saude_permanece_publica | correto | idem |
| 72 | test_e2_profissional_nao_cadastra_profissional | **inválido** (idem) | idem |
| 73 | test_e2_coordenador_cadastra_profissional | correto | idem |
| 74 | test_e2_profissional_nao_cria_turno | **inválido** (idem) | idem |
| 75 | test_e2_profissional_acessa_rota_permitida | correto | idem |
| 76 | test_e2_escrita_gera_registro | premissa (semântica de `total`) | banco: um registro, perfil `coordenador` |
| 77 | test_e2_leitura_nao_gera_registro → **test_e2_escrita_negada_por_perfil_gera_registro** | **inválido**: a E2 exige registro das escritas, mas não proíbe registrar leituras | escrita recusada com 403 gera registro com perfil `profissional` |
| 78 | test_e2_escrita_recusada_tambem_gera_registro | premissa (`total`) | banco; código 422 |
| 79 | test_e2_registro_contem_os_campos_exigidos | premissa (campos do primeiro item da listagem) | colunas e valores do registro no banco |
| 80 | test_e2_auditoria_restrita_ao_coordenador | **inválido** (chave na importação) | instância importada com as chaves |

Totais da versão 1: 13 inválidos (linhas 20, 35, 41, 42, 46, 54, 58, 68, 69,
72, 74, 77 e 80), 21 com premissa não declarada, 1 trivial (11), 6 parciais
(7, 22, 24, 40, 48 e 67) e 39 corretos. Na coleta 1, só os inválidos 35, 41,
42 e 54 chegaram a falhar: os demais dependiam de escolhas que nenhum agente
fez, como ler as chaves na importação ou omitir `GET /plantoes/{id}`. Na
coleta 2, qualquer agente poderia fazê-las.

Contagens mantidas: 54, 1, 9 e 16 testes (55, 64 e 80 por grupo). Três testes
foram substituídos um a um. `classificacao.json` fica sem testes `MUDA`: com a
suíte auditada, nenhum comportamento da suíte base muda com E1 ou E2.

## 5. Oráculo

| Defeito | Efeito possível | Correção | Efeito na coleta 1 |
|---|---|---|---|
| INV2 comparava só vizinhos na ordem de início | com plantões sobrepostos, um descanso curto podia ficar sem registro | cada plantão é comparado com o seguinte que começa depois do seu fim | nenhum: não houve sobreposição |
| Data com fuso tinha o fuso descartado, sem conversão | deslocamento de horas na comparação | conversão para UTC antes de descartar o fuso | nenhum: nenhuma violação nos estados avaliáveis, em nenhuma das versões |
| Uma violação fazia falhar todos os testes seguintes | um defeito parecia dezenas de falhas | cada teste responde pelas violações que introduz | nenhum: não houve violação |

Validação do oráculo: 42 cenários com conjunto exato de invariantes violadas
(36 da versão 1 e 6 novos). O oráculo da versão 1 falha exatamente nos 2
cenários novos que expõem seus defeitos.

## 6. Medição (`medir.py`)

| Defeito na versão 1 | Correção |
|---|---|
| Pylint, Radon, Bandit e cobertura liam configuração da pasta avaliada; o agente de r2 criou `.pylintrc` desativando quatro mensagens apontadas no relatório e ampliando os nomes aceitos por `invalid-name` | configuração fixa do instrumento (`config/`); a presença de configuração do agente é registrada |
| supressões inline (`# pylint: disable`, `# nosec`, `# pragma: no cover`) não eram contadas | colunas `pylint_supressoes`, `bandit_nosec`, `cobertura_pragmas` |
| Bandit varria a raiz; Pylint e Radon, só `app/` | Bandit restrito a `app/` |
| coleta válida com qualquer total maior que zero | só com o total exato (55, 64, 80) |
| aplicação que não importa virava "instrumento inválido" | coluna `app_importa`; é resultado do agente |
| o oráculo rodava com a pasta avaliada no caminho de importação | roda a partir da raiz do instrumento |

## 7. Orquestração (`orquestrador.py`)

| Defeito na versão 1 | Efeito observado | Correção |
|---|---|---|
| a instrução de E2 não trazia o texto de E1 | o agente removeu `noturno` como "fora da especificação" | E1 entra na instrução de E2 como alteração em vigor |
| relatório chamava de "Regressoes" todo teste reprovado | o RF34 chegou como regressão desde M1 | "Reprovados" |
| coleta impossível aparecia como "0 aprovados / 0" | r5: o agente nunca soube que a aplicação não importava | o erro de importação vai no relatório |
| teto de E1/E2 reiniciava a cada retomada | com os logs sobrescritos, o número de invocações por mudança não pode ser reconstituído | progresso persistido em `coleta/progresso/` |
| mensagem de retomada podia sugerir a repetição errada (`--inicio`) | r3 teve três inícios descartados, com M0 registrado em cada um | sugere a repetição em andamento |
| sem `--continuar`, apagava área de trabalho e `resultados.csv` | risco de perda da coleta 1 | nada é apagado; pasta, sal e etiquetas próprios |
| `interacoes.csv` sobrescrito; logs com nomes repetidos | registro parcial das invocações | gravação imediata, em modo de acréscimo; tentativa no nome do log |
| invocação que falhava deixava suas edições na área de trabalho, e o ciclo era refeito sobre elas | em r3-M1, o relatório da chamada preservada não descrevia o estado anterior congelado | edições descartadas; a invocação é refeita |
| instrumentos rodavam na área do agente | banco e caches na pasta avaliada | cópia do commit em pasta temporária |

## 8. Validação do instrumento v2

**Estados reais.** Nos estados da coleta 1 em que a aplicação carrega, a
suíte v2 e a suíte corrigida em 06/10 deram o mesmo resultado em todos os
testes que têm em comum. A única diferença está nos três testes substituídos.
Em relação à v1, os testes comuns só diferem no do RF34 (reprovado pela v1
nesses estados) e nos do RF33 e do RF36 (reprovados pela v1 nos estados em
que a fila era uma lista); dos testes substituídos, o de campos exatos
reprovava na v1 nos estados de E1 e E2 que tinham o campo `noturno`.

**Variantes que cumprem a especificação** (sobre o código de r3-E2, que passa
80/80; nenhuma pode ser reprovada):

| Variante | v1 | 06/10 | v2 |
|---|---|---|---|
| V01 RF36 devolve lista simples | reprova | passa | passa |
| V02 aceite devolve a substituição | passa* | passa | passa |
| V03 aceite sem corpo | passa* | passa | passa |
| V04 sem `GET /plantoes/{id}` | reprova | reprova | passa |
| V05 criação de turno devolve também `plantoes` | passa* | passa* | passa |
| V06 `horas_extras` como texto decimal | reprova | reprova | passa |
| V07 `horas_periodo` como texto decimal | reprova | reprova | passa |
| V08 `limite` acima de 100 reduzido a 100 | reprova | reprova | passa |
| V09 chaves da E2 lidas na importação | reprova | reprova | passa |
| V10 auditoria registra também leituras | reprova | reprova | passa |
| V11 `noturno` inválido recusado com 400 | reprova | reprova | passa |

\* o teste do RF34 (v1) e o de campos exatos (v1 e 06/10) já falham na
implementação de referência; a variante não acrescenta falha.

**Mutantes que violam uma cláusula** (cada um deve ser detectado):

| Mutante | v1 | 06/10 | v2 |
|---|---|---|---|
| M01 cancelamento não recalcula horas extras (RF22) | não | não | sim |
| M02 cancelamento não convoca (RF22) | não | sim | sim |
| M03 aceite não marca `atendida` (RF34) | não | sim | sim |
| M04 aceite fora de `convocado` (RF34) | sim | sim | sim |
| M05 RF36 devolve todos os estados | não | não | sim |
| M06 RF36 em ordem inversa | sim | sim | sim |
| M07 RF33 apaga em vez de cancelar | não | não | sim |
| M08 RF33 não reordena | sim | sim | sim |
| M09 aprovação sem `data_decisao` (RF25) | não | não | sim |
| M10 rejeição sem `data_decisao` (RF26) | não | não | sim |
| M11 sem rejeição automática (RF28) | sim | sim | sim |
| M12 filtro de trocas ignorado (RF29) | não | não | sim |
| M13 RF07 não remove o vínculo | não | não | sim |
| M14 `limite` sem máximo (RF04) | sim | sim | sim |
| M15 exclui turno com plantão (RF12) | sim | sim | sim |
| M16 filtro `noturno` ignorado (E1) | sim | sim | sim |
| M17 sem adicional noturno (E1) | sim | sim | sim |
| M18 `noturno` padrão verdadeiro (E1) | sim | sim | sim |
| M19 escrita negada não auditada (E2) | não | não | sim |
| M20 perfil errado com autenticação desativada (E2) | sim | sim | sim |
| M21 dois registros por escrita (E2) | sim | sim | sim |
| M22 auditoria aberta ao profissional (E2) | sim | sim | sim |
| M23 profissional cria turno (E2) | sim | sim | sim |
| **Total detectado** | **13/23** | **15/23** | **23/23** |

## 9. Efeito sobre os dados da coleta 1

Ver `reavaliacao-v1/resumo.txt`, gerado por `reavaliar_v1.py`, e o complemento
do capítulo de resultados.
