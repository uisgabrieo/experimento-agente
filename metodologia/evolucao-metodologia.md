# Decisões de evolução

## Evolução 1

### Objetivo da evolução

Avaliar a capacidade do agente de incorporar uma mudança pequena e localizada ao sistema, observando como ele adapta a implementação existente sem provocar alterações desnecessárias em outras partes da aplicação.

### Por que a mudança é localizada

A evolução afeta principalmente o modelo de `Turno`, o schema de validação, o cálculo de horas e o filtro da listagem de turnos. A expectativa inicial é de alteração em aproximadamente 3 a 5 arquivos.

### Decisão metodológica

O campo `noturno` foi definido como opcional e com valor padrão `false` para preservar a compatibilidade com os casos de teste existentes. Caso o campo fosse obrigatório, as criações de turno que não o informassem passariam a retornar 422, fazendo com que uma parcela significativa da suíte deixasse de representar regressão e passasse a exigir mudança de comportamento.

O adicional de 20% incide exclusivamente sobre o campo `horas_periodo` retornado pela consulta da escala do profissional. Não interfere em `horas_extras` (`INV8`) nem no limite semanal (`INV3`), que continuam sendo calculados com base na duração real dos plantões.

Esta delimitação decorre de conflito identificado durante a validação prévia dos instrumentos: `horas_extras` é campo governado por invariante, verificada por oráculo congelado que a recalcula a partir da duração real. Caso o adicional incidisse sobre ele, toda aplicação que implementasse E1 corretamente seria acusada de violar `INV8`, e a evolução jamais atingiria o critério de aceitação. A distinção entre regra de apresentação e regra de consistência foi, portanto, tornada explícita antes do congelamento.

Essa distinção foi definida previamente para evitar interpretações diferentes durante a implementação da evolução.

### Classificação dos testes

Na coleta 1, `test_rf09_campos_exatos_do_turno` era o único teste classificado como `MUDA`, porque exigia o conjunto exato de campos do turno. A auditoria do instrumento (ver `auditoria-instrumento-v2.md`) concluiu que essa exigência não decorre da especificação: a seção 2.1 admite colunas adicionais e o RF09 não define o corpo da resposta. Na versão 2, o teste foi substituído por `test_rf09_duracoes_de_4h_e_12h_aceitas`.

Com a suíte auditada, nenhum comportamento verificado pela suíte base muda com E1, que manda não alterar nenhum outro comportamento. Todos os testes existentes são `MANTEM`, e `classificacao.json` não lista testes `MUDA`.

---

## Evolução 2

### Objetivo da evolução

Avaliar o comportamento do agente diante de uma alteração transversal, isto é, uma mudança que se espalha por diferentes partes da aplicação e exige adaptações em vários pontos da implementação.
A evolução foi definida dessa forma para observar como o agente lida com uma mudança de maior alcance, especialmente quando precisa preservar o comportamento já existente enquanto introduz novas responsabilidades no sistema, com o esperado de não introdução de falhas.

### Por que a mudança é transversal

A autenticação afeta todas as rotas da aplicação. A diferenciação por perfil de usuário interfere em um subconjunto dessas rotas, enquanto a auditoria alcança todas as operações de escrita e ainda acrescenta uma nova entidade ao sistema.

Diferentemente da Evolução 1, portanto, a alteração não fica concentrada em um modelo ou fluxo específico. A expectativa inicial é de que mais de 10 arquivos precisem ser modificados.

### Decisão metodológica

Foi definido que, caso nenhuma das variáveis de ambiente relacionadas à autenticação esteja configurada, a autenticação deve permanecer desativada.

Essa decisão preserva a possibilidade de utilizar a suíte de testes anterior como medida de regressão. Sem essa condição, os testes existentes passariam a receber respostas 401 por não fornecerem credenciais. Essas falhas seriam consequência esperada do novo requisito, e não regressões introduzidas pela evolução, o que comprometeria a interpretação do indicador.

A autenticação permanecer desativada durante a execução da suíte anterior, mas isso não reduz o caráter transversal da evolução. A implementação ainda precisa incorporar autenticação, controle de acesso por perfil e auditoria nos diferentes pontos previstos pelo novo requisito. O que se evita é apenas que a mudança esperada no mecanismo de acesso invalide a comparação com o comportamento anterior.

### Classificação dos testes

Todos os testes da suíte base e da Evolução 1 permanecem classificados como `MANTEM`.

Esses testes são executados sem as variáveis de ambiente de autenticação definidas. Nessas condições, a aplicação deve preservar o comportamento anterior.

Os testes específicos da Evolução 2 ficam responsáveis por verificar o funcionamento da autenticação, das restrições por perfil e da auditoria quando a nova configuração estiver habilitada.

---

## Caracterização esperada das evoluções

Antes da execução, as duas evoluções são caracterizadas da seguinte forma:

| Indicador               | Evolução 1 | Evolução 2                |
| ----------------------- | ---------- | ------------------------- |
| Alcance da mudança      | localizado | transversal               |
| Arquivos modificados (esperados)   | 3 a 5      | mais de 10                |
| Linhas alteradas        | dezenas    | centenas                  |
| Iterações até aceitação | poucas     | maior quantidade esperada |

Esses valores representam uma expectativa anterior à execução e serão utilizados apenas como referência descritiva.

Não se pretende estabelecer uma relação causal entre o caráter localizado ou transversal da evolução e o custo observado durante sua implementação. A Evolução 2 foi construída deliberadamente com um escopo maior que o da Evolução 1. Dessa forma, uma eventual diferença no número de arquivos modificados, linhas alteradas ou iterações necessárias pode decorrer tanto da natureza transversal da mudança quanto de seu próprio volume. 

A intenção dessas evoluções é observar e analisar como o agente responde a mudanças de diferentes alcances durante os ciclos de desenvolvimento, considerando sua capacidade de adaptar a aplicação sem comprometer o comportamento já existente.

Por esse motivo, a comparação entre E1 e E2 será tratada como **caracterização descritiva do comportamento observado**, e não como evidência de que mudanças transversais, por si só, causam maior custo de evolução.
