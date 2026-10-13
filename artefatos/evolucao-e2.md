## 1. Autenticação por perfil
Toda rota, exceto GET /saude, passa a exigir o cabeçalho X-Auth-Key.

As chaves válidas são lidas das variáveis de ambiente CHAVE_COORDENADOR e CHAVE_PROFISSIONAL. Cada chave identifica, respectivamente, os perfis coordenador e profissional.

Se nenhuma das duas variáveis estiver definida, a autenticação fica desativada e as rotas existentes mantêm o comportamento anterior. Se pelo menos uma delas estiver definida, a autenticação fica ativa e somente as chaves correspondentes às variáveis definidas são consideradas válidas.

Com a autenticação ativa, a ausência do cabeçalho X-Auth-Key retorna 401 (Unauthorized) e uma chave não reconhecida retorna 403 (Forbidden).

As operações de aprovação e rejeição de troca, criação e remoção de turnos e cadastro de profissionais exigem o perfil coordenador. O acesso a essas operações com o perfil profissional retorna 403 (Forbidden).

## 2.Registro de auditoria
Toda requisição a uma operação de escrita deve gerar um registro na tabela auditoria, independentemente de a operação terminar com sucesso ou com resposta 4xx.

A tabela deve conter id, metodo, caminho, perfil, codigo_resposta e instante. O instante deve seguir as mesmas convenções de data e hora definidas na especificação.

Quando a autenticação estiver ativa, perfil deve registrar coordenador ou profissional, conforme a chave utilizada. Quando estiver desativada, o campo deve registrar desativada.

O próprio registro da auditoria não deve gerar uma nova entrada de auditoria.

Acrescente a rota GET /auditoria, que retorna {itens, total} e é restrita ao perfil coordenador quando a autenticação estiver ativa. Quando a autenticação estiver desativada, essa rota pode ser acessada sem X-Auth-Key, assim como as demais.