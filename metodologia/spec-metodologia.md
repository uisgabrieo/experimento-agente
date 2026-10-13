# Metodologia aplicada

## 1. Tema

Qualidade interna, preservação de invariantes e capacidade de absorção de mudanças em aplicação gerada por agente de inteligência artificial: um estudo de caso com execuções repetidas sobre ciclos automatizados de autocorreção.

## 2. Autoria e uso de inteligência artificial (IA) nos artefatos

As especificações e as decisões relacionadas ao sistema a ser desenvolvido foram elaboradas pelo autor da pesquisa. Foi utilizada uma ferramenta de inteligência artificial (ChatGPT) como apoio à revisão textual, à análise dos requisitos definidos em `spec.md` e à verificação da consistência e da coesão do documento.

A definição do sistema, de seu escopo, dos requisitos e das decisões metodológicas permanece sob responsabilidade do autor.

## 3. Intuito das especificações no experimento

Para o experimento, foi elaborada uma especificação para o desenvolvimento de um sistema de gerenciamento de escalas de plantão de uma clínica.

Depois de congelada, a especificação não poderá ser alterada retroativamente, de forma a preservar as condições definidas para o experimento. Ambiguidades identificadas durante as execuções serão registradas e discutidas posteriormente no trabalho.

O agente responsável pela codificação (Claude Code, na versão registrada no manifesto de cada coleta) recebe apenas os arquivos necessários para a implementação, contendo as regras, os requisitos e as limitações do sistema. O `oraculo`, a suíte de `testes` e os demais componentes responsáveis pela avaliação permanecem fora de sua área de trabalho.

## 4. Informações ocultadas do agente

Durante as execuções, o agente não possui acesso às seguintes informações:

* suíte de testes;
* oráculo de invariantes;
* orquestrador dos ciclos de implementação e correção;
* quantidade total de ciclos;
* quantidade de execuções do experimento;
* classificação dos testes entre `MANTEM` e `MUDA`;
* métricas utilizadas na análise;
* expectativas de mudanças ao longo dos ciclos;
* tema e objetivos do TCC;
* evoluções que ainda não tenham sido disponibilizadas;
* decisões metodológicas definidas para E1 e E2;
* resultados das demais execuções.

O agente recebe a identidade nominal dos testes aprovados e reprovados nos relatórios de verificação, uma vez que essa informação é necessária para orientar a correção. Não recebe, contudo, o código dos testes, as fixtures, as asserções, os dados internos da suíte nem a implementação do oráculo.

Essas medidas foram adotadas para reduzir a possibilidade de o agente adaptar antecipadamente sua estratégia de implementação ao mecanismo de avaliação ou às mudanças que ainda não lhe foram apresentadas.

### 4.1 Isolamento estrutural

A área de trabalho do agente está em árvore de diretórios diferente daquela que abriga o oráculo, as suítes e os demais artefatos da pesquisa. Dessa forma, esses componentes não são alcançáveis a partir do diretório em que o agente opera.

O orquestrador interrompe a execução caso a área de trabalho esteja na árvore de pesquisa, de modo que a separação não dependa de configuração correta a cada execução.

Os diretórios de trabalho recebem identificadores a partir de função de hash, e não o índice sequencial da repetição. Assim, o nome do próprio diretório não revela ao agente o número da execução em que está atualmente e nem a existência de execuções anteriores.

## 5. Oráculo e schema

O `oraculo` verifica as invariantes por meio de consultas diretas ao banco de dados. Em razão disso, a **seção 2.1** de `spec.md` determina que os nomes das tabelas e colunas definidos na especificação devem ser obrigatoriamente usados pela implementação.

A existência do `oraculo` e sua forma de acesso ao banco não são informadas ao agente. Para o agente, a estrutura definida na seção 2.1 é apresentada apenas como parte do contrato técnico da aplicação.

## 6. Verificação das invariantes

As invariantes são verificadas externamente por meio do `oraculo`. A aplicação gerada não é responsável pela avaliação utilizada na pesquisa.

O agente conhece as invariantes, pois elas fazem parte dos requisitos funcionais e das regras de consistência do sistema. Entretanto, não é informado sobre a existência do `oraculo` utilizado posteriormente para verificar sua preservação.

Essa separação permite que o agente implemente as regras conhecendo apenas o comportamento esperado do sistema, sem conhecer o mecanismo externo usado para avaliá-lo.

## 7. Instrução de inicialização

A geração inicial do sistema é iniciada com o seguinte prompt:

```text
Implemente integralmente o sistema descrito na especificação em anexo. Respeite todas as restrições técnicas da seção 2, incluindo o esquema de banco da seção 2.1 e o ponto de entrada `app/main.py` com o objeto `app`. As oito invariantes da seção 4 devem valer após qualquer operação.
```

## 8. Ciclos de correção

A instrução utilizada nos cinco ciclos de correção (M1 a M5) é:

```text
Seguem os relatórios de análise do projeto. Corrija os problemas apontados. Não altere o comportamento funcional descrito na especificação.

{relatorios}
```

Os relatórios anexados reúnem a análise estática (Pylint, Radon e Bandit) e o relatório estruturado de verificação produzido externamente, contendo as contagens de testes aprovados e reprovados e as invariantes violadas, sem exposição do código dos testes.

### 8.1 Iterações das evoluções

A partir da segunda iteração de cada evolução, quando a anterior não satisfez o critério de aceitação, a instrução utilizada é:

```text
Segue o relatório de verificação. Corrija as falhas e regressões apontadas sem alterar o comportamento funcional descrito na especificação.

{relatorio}
```

Trata-se de uma instrução diferente da empregada nos ciclos de correção, uma vez que o relatório correspondente separa as falhas relativas ao requisito novo das regressões em comportamento anteriormente aprovado.

A instrução é mantida igual entre os ciclos e entre as diferentes execuções. O número do ciclo e a quantidade total de ciclos não são informados ao agente.

Os relatórios encaminhados ao agente contêm somente as informações de correção previstas no protocolo experimental, sem expor o código dos testes, seus nomes, a estrutura interna do `oraculo` ou outros elementos privados utilizados na avaliação.

## 9. Evoluções

As evoluções permanecem fora da área de trabalho do agente até o momento em que cada uma delas é aplicada.

Durante a geração inicial, o agente não recebe informações sobre E1 ou E2. No início de E1, recebe somente a instrução correspondente a essa evolução. E2 é apresentada apenas após o encerramento da etapa anterior.

As justificativas para a classificação das evoluções como localizada ou transversal, as expectativas quanto à quantidade de arquivos modificados, a classificação dos testes e as demais decisões relacionadas ao desenho dessas mudanças permanecem registradas separadamente em `evolucao-metodologia.md`.

## 10. Registro de ambiguidades

Ambiguidades identificadas durante as execuções são registradas pelo autor da pesquisa sem alteração retroativa da especificação utilizada naquela execução.

| Data | RF | Ambiguidade | Como o agente resolveu |
| ---- | -- | ----------- | ---------------------- |
|      |    |             |                        |
