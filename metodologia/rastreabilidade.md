# Matriz de rastreabilidade

Gerada por `rastreabilidade.py` a partir da especificação e das suítes.

> **Alcance desta matriz.** A associação é feita por menção ao
> identificador do requisito no nome ou no corpo do teste. Ela
> demonstra **rastreabilidade** — que existe ao menos um teste
> referente a cada requisito — e não cobertura integral do
> comportamento especificado. Um requisito com múltiplas condições
> pode constar como rastreado ainda que apenas parte delas seja
> exercitada.

## Requisitos funcionais

| Requisito | Testes | Situação |
|---|---|---|
| RF01 | 1 | rastreado |
| RF02 | 6 | rastreado |
| RF03 | 2 | rastreado |
| RF04 | 3 | rastreado |
| RF05 | 2 | rastreado |
| RF06 | 2 | rastreado |
| RF07 | 2 | rastreado |
| RF08 | 2 | rastreado |
| RF09 | 6 | rastreado |
| RF10 | 2 | rastreado |
| RF11 | 3 | rastreado |
| RF12 | 2 | rastreado |
| RF13 | 1 | rastreado |
| RF14 | 1 | rastreado |
| RF15 | 1 | rastreado |
| RF16 | 2 | rastreado |
| RF17 | 1 | rastreado |
| RF18 | 1 | rastreado |
| RF19 | 1 | rastreado |
| RF20 | 1 | rastreado |
| RF21 | 1 | rastreado |
| RF22 | 2 | rastreado |
| RF23 | 2 | rastreado |
| RF24 | 2 | rastreado |
| RF25 | 2 | rastreado |
| RF26 | 1 | rastreado |
| RF27 | 1 | rastreado |
| RF28 | 1 | rastreado |
| RF29 | 1 | rastreado |
| RF30 | 3 | rastreado |
| RF31 | 2 | rastreado |
| RF32 | 1 | rastreado |
| RF33 | 3 | rastreado |
| RF34 | 2 | rastreado |
| RF35 | 2 | rastreado |
| RF36 | 1 | rastreado |
| RF37 | 2 | rastreado |
| RF38 | 1 | rastreado |

**38 de 38 requisitos rastreados.**

## Invariantes

| Invariante | Testes na suíte | Validação do oráculo |
|---|---|---|
| INV1 | 1 | 8 |
| INV2 | 0 | 11 |
| INV3 | 0 | 5 |
| INV4 | 1 | 3 |
| INV5 | 0 | 10 |
| INV6 | 1 | 6 |
| INV7 | 0 | 12 |
| INV8 | 3 | 10 |

## Detalhamento por requisito

**RF01**
- `base/test_cadastros::test_rf01_criar_profissional`

**RF02**
- `base/test_cadastros::test_rf02_carga_semanal_abaixo_do_minimo`
- `base/test_cadastros::test_rf02_carga_semanal_acima_do_maximo`
- `base/test_cadastros::test_rf02_email_curto_demais`
- `base/test_cadastros::test_rf02_email_sem_arroba`
- `base/test_cadastros::test_rf02_nome_vazio`
- `e1/test_noturno::test_e1_valor_invalido_recusado`

**RF03**
- `base/test_cadastros::test_rf02_carga_semanal_abaixo_do_minimo`
- `base/test_cadastros::test_rf03_email_duplicado`

**RF04**
- `base/test_cadastros::test_rf03_email_duplicado`
- `base/test_cadastros::test_rf04_limite_maximo_de_100`
- `base/test_cadastros::test_rf04_listar_profissionais`

**RF05**
- `base/test_cadastros::test_rf03_email_duplicado`
- `base/test_cadastros::test_rf05_consultar_profissional_inexistente`

**RF06**
- `base/test_cadastros::test_rf05_consultar_profissional_inexistente`
- `base/test_cadastros::test_rf06_vinculo_duplicado`

**RF07**
- `base/test_complementares::test_rf07_remover_especialidade_com_plantao_confirmado`
- `base/test_complementares::test_rf07_remover_especialidade_sem_plantao`

**RF08**
- `base/test_cadastros::test_rf05_consultar_profissional_inexistente`
- `base/test_cadastros::test_rf08_especialidade_duplicada`

**RF09**
- `base/test_turnos::test_rf09_criar_turno`
- `base/test_turnos::test_rf09_duracao_curta_recusada`
- `base/test_turnos::test_rf09_duracao_longa_recusada`
- `base/test_turnos::test_rf09_duracoes_de_4h_e_12h_aceitas`
- `base/test_turnos::test_rf11_consultar_turno_inexistente`
- `e1/test_noturno::test_e1_valor_invalido_recusado`

**RF10**
- `base/test_turnos::test_rf09_duracao_longa_recusada`
- `base/test_turnos::test_rf10_listar_turnos`

**RF11**
- `base/test_complementares::test_rf12_excluir_turno_sem_plantao`
- `base/test_turnos::test_rf09_duracao_longa_recusada`
- `base/test_turnos::test_rf11_consultar_turno_inexistente`

**RF12**
- `base/test_complementares::test_rf12_excluir_turno_com_plantao_confirmado`
- `base/test_complementares::test_rf12_excluir_turno_sem_plantao`

**RF13**
- `base/test_alocacao::test_rf13_alocar_plantao`

**RF14**
- `base/test_alocacao::test_rf14_sem_especialidade`

**RF15**
- `base/test_alocacao::test_rf15_sobreposicao`

**RF16**
- `base/test_alocacao::test_rf16_descanso_de_exatamente_11h_permitido`
- `base/test_alocacao::test_rf16_descanso_menor_que_11h`

**RF17**
- `base/test_alocacao::test_rf17_excede_44_horas_semanais`

**RF18**
- `base/test_alocacao::test_rf18_sobreposicao_com_ausencia`

**RF19**
- `base/test_alocacao::test_rf19_setimo_dia_consecutivo`

**RF20**
- `base/test_alocacao::test_rf20_profissional_inativo`

**RF21**
- `base/test_alocacao::test_rf21_ja_alocado_no_mesmo_turno`

**RF22**
- `base/test_alocacao::test_rf22_cancelamento_libera_horas`
- `base/test_complementares::test_rf34_aceite_cria_plantao`

**RF23**
- `base/test_complementares::test_rf23_consultar_escala`
- `base/test_complementares::test_rf23_escala_respeita_o_periodo`

**RF24**
- `base/test_complementares::test_rf24_troca_com_plantao_cancelado`
- `base/test_complementares::test_rf24_troca_entre_plantoes_do_mesmo_profissional`

**RF25**
- `base/test_trocas::test_rf25_troca_invalida_nao_altera_nada`
- `base/test_trocas::test_rf25_troca_valida_permuta_os_dois`

**RF26**
- `base/test_trocas::test_rf27_decidir_troca_ja_decidida`

**RF27**
- `base/test_trocas::test_rf27_decidir_troca_ja_decidida`

**RF28**
- `base/test_complementares::test_rf28_cancelamento_rejeita_troca_automaticamente`

**RF29**
- `base/test_complementares::test_rf29_listar_trocas_com_filtro`

**RF30**
- `base/test_complementares::test_rf34_aceite_cria_plantao`
- `base/test_substituicoes::test_rf30_entrar_na_fila`
- `base/test_substituicoes::test_rf30_segunda_inscricao_recebe_posicao_2`

**RF31**
- `base/test_complementares::test_rf34_aceite_cria_plantao`
- `base/test_substituicoes::test_rf31_cobertura_ja_atendida`

**RF32**
- `base/test_substituicoes::test_rf32_sem_especialidade`

**RF33**
- `base/test_substituicoes::test_rf32_sem_especialidade`
- `base/test_substituicoes::test_rf33_cancelamento_reordena_a_fila`
- `base/test_substituicoes::test_rf33_cancelar_inscricao`

**RF34**
- `base/test_complementares::test_rf34_aceite_cria_plantao`
- `base/test_complementares::test_rf34_aceite_fora_do_estado_convocado`

**RF35**
- `base/test_alocacao::test_rf18_sobreposicao_com_ausencia`
- `base/test_substituicoes::test_rf35_ausencia_com_plantao_sobreposto`

**RF36**
- `base/test_substituicoes::test_rf36_consultar_fila`

**RF37**
- `base/test_transversais::test_rf37_erro_404_contem_detail`
- `e1/test_noturno::test_e1_valor_invalido_recusado`

**RF38**
- `base/test_transversais::test_rf38_rota_de_saude`
