# Auto-revisão de segurança

**Estado:** auto-revisão feita pelo próprio executor. Não é revisão independente; a revisão independente (tarefa 10.5) continua pendente para o supervisor.

Âmbito: autorização, aprovação, injecção, memória, API e configuração. Método: leitura do código e dos testes, e verificação dos pontos abaixo.

## Verificado e OK (com teste)

- Isolamento por tenant em tarefas, aprovações, memória e ferramentas. Outro tenant recebe `404` idêntico a inexistente (`tests/test_api_tasks.py`, `tests/test_tools_handlers.py`, `tests/test_memory.py`).
- Requester não resolve aprovações, nem as suas (`403`) (`test_requester_cannot_resolve_even_own_approval`).
- Ferramentas: allowlist, schemas com `extra="forbid"`, valores inválidos não são ecoados (`tests/test_tools_executor.py`).
- Consultas com `icontains(autoescape=True)` e ORM; sem SQL construído por concatenação.
- Metadados de eventos e métricas não incluem corpo de tickets (verificado no código de `tool_call`).
- Memória: eliminação só pelo dono; filtro de escrita bloqueia segredos e dados pessoais e regista o motivo.
- Dados que vêm das ferramentas entram no prompt do provider real **delimitados** como dados não confiáveis (`_delimited` em `backend/app/agents/llm.py`). Corrigido nesta revisão: o wrapper existia mas não estava ligado.
- Efeito com erro de negócio termina a tarefa como `failed` em vez de a deixar em `running` (corrigido nesta revisão).

## Achados em aberto

1. **`DEMO_MODE` tem omissão `true`** (`backend/app/config.py`). O login por persona sem palavra-passe fica activo por omissão. Risco alto se a API for exposta. Recomendação: omissão `false` e exigir activação explícita.
2. **Segredo JWT predefinido.** `jwt_secret` tem um valor público no código. Qualquer instância que não o substitua aceita tokens forjados. Recomendação: recusar arranque com `demo_mode=false` e segredo predefinido. Não implementado.
3. **Gancho de teste em código de produção.** `CRASH_AT_NODE` faz o processo terminar. Se definido por engano num worker, derruba execuções. Recomendação: só ativo com `APP_ENV=test`. Não implementado.
4. **Injecção: defesa estrutural, não por padrões.** O varrimento de padrões (`backend/app/tools/injection.py`) é heurístico e fácil de contornar. A protecção real é a aprovação obrigatória para acções mutáveis e a autorização no backend. Um modelo que siga instruções pode propor acções erradas; o revisor é o controlo.
5. **Validação de edição não verifica tenant no momento da edição.** `validate_edit` não confirma que o `user_id` pertence ao tenant. A execução (`_perform`) confirma e devolve `not_found`, por isso não há efeito cruzado, mas o revisor vê um pedido inválido só depois.
6. **Imutabilidade da auditoria é aplicacional.** `approval_audit` não tem gatilhos na base de dados; um acesso directo à base de dados pode alterar linhas. Recomendação: permissões de base de dados (só `INSERT`) e encadeamento de hashes.
7. **Filtro de memória por padrões.** Dados pessoais em formatos não previstos passam. Não há medição de falsos negativos.
8. **Retenção de dados.** Pedidos, resultados e checkpoints ficam guardados sem prazo. Não há política de retenção para tarefas (só para memória, com TTL).
9. **Sem limite de taxa nem CORS configurado** na API. Não há autenticação por serviço para o worker.
10. **Sem revisão de dependências** (`pip-audit`) nesta entrega.
11. **Dados de teste em tokens de demonstração**: `joao@nimbo` e outros são personas sintéticas; não há credenciais reais no repositório.

## Ações tomadas nesta revisão

- Ligação do wrapper de dados não confiáveis ao provider real, com teste (`test_observations_are_sent_as_delimited_untrusted_data`).
- Captura do erro de efeito no nó de execução, com teste indirecto pela suite existente.

## Recomendação ao supervisor

Antes de qualquer exposição: resolver os achados 1, 2 e 3 (são pequenos e bloqueantes), e pedir revisão independente focada em aprovação (`human-approval`) e injecção (`agent-tools`).
