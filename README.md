# Qualidade interna, preservação de invariantes e capacidade de absorção de mudanças em aplicação gerada por agente de inteligência artificial

Material do Trabalho de Conclusão de Curso de Luís Gabriel Salvador Barros
(Engenharia de Software, iCEV, 2026): o instrumento experimental e os dados
da coleta 2 analisados no texto. É o pacote de evidências citado no texto
como `Evidencias_TCC_V023`.

## Desenho, em resumo

Cada repetição gera uma API REST de gestão de escalas de plantão a partir de
uma especificação fixa (M0), passa por cinco ciclos fixos de autocorreção
alimentados por relatórios externos (M1 a M5) e incorpora duas mudanças (E1,
localizada; E2, transversal), com até cinco tentativas cada. Uma suíte externa
(55, 64 e 80 testes), um oráculo de oito invariantes por leitura do banco,
Pylint, Radon, Bandit e cobertura medem cada estado. O agente não vê o
instrumento.

## Onde está cada coisa

| Caminho | Conteúdo |
|---|---|
| etiqueta `EXPERIMENTO-V2-CONGELADO` (commit `9dd4c8d4453cedf24ac3146b322a711f9542404c`) | instrumento congelado antes da primeira execução |
| `artefatos/` | especificação e requisitos de mudança E1 e E2 |
| `oracle/`, `validacao_oraculo/` | testes externos, oráculo de invariantes e sua validação |
| `orquestrador.py`, `orq/`, `medir.py`, `config/` | orquestrador dos ciclos, medidor e configurações das ferramentas |
| `metodologia/` | auditoria do instrumento, protocolo de execução e rastreabilidade |
| `manifesto-experimento.json`, `requirements-congelado.txt` | condições, versões e hashes registrados antes da coleta |
| `coleta/` | dados da coleta 2: `estados.csv`, `resultados.csv`, `evolucoes.csv`, `interacoes.csv`, relatórios JSON e JUnit de cada estado e registros de cada chamada ao agente |
| `reavaliacao-v1/` | reavaliação dos estados da coleta 1 com o instrumento v2 (`reavaliar_v1.py`) |
| `simulacao/` | ensaio do orquestrador com agente simulado, antes da coleta |
| `execucoes-v2/` | código produzido pelo agente: uma área por repetição, com todo o histórico Git |
| `codigo/` | cópias do código dos estados citados no texto (r2-M0, r2-M1, r4-M2, r4-M3, r1-E2) e `commits.csv` com os hashes completos |
| `complementar/` | testes complementares da Seção 2.12: `confirmacao1/` e `confirmacao2/` (resultados, eventos HTTP, ambiente e dependências) e `sources_manifest.json` |
| `LEIA-ME.txt` | roteiro para conferir dois resultados citados no texto |
| `SHA256SUMS.txt` | SHA-256 de cada arquivo versionado |

## Código produzido pelo agente

Cada arquivo de `execucoes-v2/` é um *git bundle* com o histórico completo de
uma repetição: um commit por estado e as etiquetas usadas pelo orquestrador.
Os commits citados no texto podem ser conferidos assim:

```
git clone execucoes-v2/r4-4352363dbf.bundle r4
cd r4
git log --oneline --all
```

| Repetição | Arquivo |
|---|---|
| r1 | `execucoes-v2/r1-f53eb64fb5.bundle` |
| r2 | `execucoes-v2/r2-1be53be64a.bundle` |
| r3 | `execucoes-v2/r3-797466c277.bundle` |
| r4 | `execucoes-v2/r4-4352363dbf.bundle` |
| r5 | `execucoes-v2/r5-42033f96ae.bundle` |

O `coleta/interacoes.csv` traz as 48 chamadas de r1 a r5 (40 concluídas e oito interrompidas).
