# 06 — Ferramentas, autorização e defesa contra tool injection

## O problema

Um agente LLM decide *o que* chamar, mas não deve decidir *o que pode* fazer. Se o modelo escolher o tenant, o papel, ou se conseguir chamar uma ferramenta que não lhe pertence, qualquer texto malicioso num ticket pode transformar-se numa acção sobre uma conta real. Este módulo trata três coisas: uma allowlist de ferramentas tipadas, autorização feita no backend com a identidade do requester, e tratamento do conteúdo dos tickets como dado não confiável.

## O que entra e o que sai

Entrada: uma chamada `{"tool": ..., "args": {...}}` produzida pelo modelo, mais o contexto de execução (`ToolContext`: tenant, utilizador, papel, tarefa, agente, sessão e emissor de eventos). O contexto vem do backend, nunca do modelo.

Saída: um `ToolOutcome` com `ok`, `error` (código curto), `data` (ferramentas de leitura), `proposal` (ferramentas mutáveis) e `suspicious` (padrões de instrução encontrados).

Saída real de uma execução sobre a base demo (seed sintético, tenant `nimbo`), reproduzida pelo executor:

```text
delete_all_tickets agent= triage -> unknown_tool [('tool_call', {'status': 'error', 'code': 'unknown_tool'})]
get_ticket agent= triage -> invalid_arguments [('tool_call', {'status': 'error', 'code': 'invalid_arguments', 'fields': ['ticket_id']})]
propose_account_action agent= reporting -> tool_not_allowed [('tool_call', {'status': 'error', 'code': 'tool_not_allowed'})]
get_ticket agent= triage -> not_found [('tool_call', {'status': 'error', 'code': 'not_found'})]
get_ticket agent= triage -> ok [('suspected_injection', {'patterns': ['impersonates_admin', 'auto_approve', 'ignore_instructions']}), ('tool_call', {'status': 'ok'})]
```

Repare que `get_ticket("ATL-9")` a partir de `nimbo` devolve `not_found`, exactamente como um id inexistente, e que a mensagem de argumentos inválidos indica apenas o campo (`ticket_id`), sem ecoar o valor enviado.

## Como funciona por dentro

A ordem das verificações está fixa em `backend/app/tools/executor.py:53` (`execute_tool`):

1. **Allowlist.** Se o nome não existe no registo (`REGISTRY`, em `backend/app/tools/registry.py`), a chamada termina em `unknown_tool` (linha 59). Nada mais é avaliado.
2. **Âmbito do agente.** Cada `ToolSpec` declara `allowed_agents`. `reporting` não está em `propose_account_action`, por isso a linha 62 devolve `tool_not_allowed`.
3. **Papel.** `allowed_roles` é verificado antes de tocar em dados.
4. **Validação do schema.** `model_validate` (linha 72) com `extra="forbid"`. Campos extra, como `tenant_id` injectado pelo modelo, são rejeitados. Os erros expõem apenas os nomes dos campos.
5. **Execução com tenant do contexto.** Os handlers (`backend/app/tools/handlers.py`) recebem `ctx.tenant_id`. `_scoped` (linha 18) devolve `ToolError("not_found")` quando o registo é de outro tenant, indistinguível de um registo inexistente.
6. **Validação da saída.** O resultado passa pelo `output_model` antes de ser devolvido.
7. **Varrimento de conteúdo não confiável.** `scan_untrusted` (`backend/app/tools/injection.py:47`) procura padrões de instrução nas strings da saída e emite `suspected_injection`.

As ferramentas mutáveis (`propose_ticket_status`, `propose_account_action`) **não alteram dados**. Devolvem uma proposta. A alteração só acontece em `apply_effect` (`backend/app/tools/effects.py:60`), depois de uma aprovação humana (grupo 5).

## Porquê esta escolha

- **Autorização no backend.** A segurança não depende de o modelo "se portar bem". Mesmo que o modelo peça outro tenant, o handler só consulta linhas do tenant do contexto.
- **Erro indistinguível.** Devolver `403` para registos de outro tenant revelaria que o id existe. Por isso `not_found` para os dois casos.
- **Schema estrito.** `extra="forbid"` transforma tentativas de injectar parâmetros em erros explícitos e registados.
- **Proposta antes de efeito.** A ferramenta mutável não tem caminho para o efeito; isto torna a aprovação uma propriedade estrutural e não uma convenção.

## Alternativas

- **Deixar o modelo escolher o tenant e confiar na resposta.** Rejeitada: um único erro de prompt quebra o isolamento.
- **Filtrar injecção só por regex.** Insuficiente: a regex é uma heurística. Por isso a regex só regista `suspected_injection`; a defesa real é a aprovação obrigatória e a autorização.
- **Chamadas nativas de function-calling sem allowlist própria.** Funcionaria com um provider, mas o registo próprio dá um ponto único de verificação e testes independentes do provider.

## Como falha (e onde está testado)

| Regra | Teste |
|---|---|
| Ferramenta inexistente → `unknown_tool` | `tests/test_tools_executor.py::test_unknown_tool_is_refused_and_recorded` |
| Argumentos inválidos falham antes de qualquer acesso a dados; valor não é ecoado | `test_invalid_ticket_id_fails_before_any_data_access` |
| Campos extra rejeitados | `test_extra_fields_are_rejected`, `test_tenant_comes_from_context_not_from_arguments` |
| Agente fora do âmbito → `tool_not_allowed` e sem execução | `test_reporting_calling_account_action_is_tool_not_allowed` |
| Ticket de outro tenant → `not_found` | `tests/test_tools_handlers.py::test_get_ticket_from_other_tenant_is_not_found` |
| `not_found` idêntico a inexistente | `test_get_ticket_missing_and_foreign_look_identical` |
| Pesquisa e procedimentos com escopo de tenant | `test_search_tickets_only_returns_own_tenant`, `test_search_procedures_is_tenant_scoped` |
| Citação de procedimento de outro tenant recusada | `test_draft_reply_rejects_citation_from_other_tenant` |
| Proposta não altera dados | `test_proposal_does_not_change_data_until_effect_is_applied` |
| Utilizador de outro tenant em acção de conta → `not_found` | `test_account_action_on_other_tenant_user_is_not_found` |
| Efeito aplicado no máximo uma vez para a mesma chave | `test_effect_is_applied_once_for_same_key` |
| Ticket malicioso marcado como `suspected_injection` | `test_malicious_ticket_is_flagged_as_suspected_injection` |

Limitação conhecida: a heurística de injecção cobre padrões em português e inglês escritos de forma conhecida. Um atacante com outra formulação passa a heurística; a garantia continua a ser a aprovação humana para qualquer acção mutável.

## Perguntas de entrevista

1. **Porque é que a autorização não pode ficar no prompt?** Porque o prompt é entrada controlada por dados não confiáveis. A autorização tem de ser código que lê a identidade do contexto e não o texto do modelo.
2. **Porque devolver `not_found` em vez de `forbidden` para outro tenant?** Para não revelar a existência do recurso (enumeração de ids).
3. **O que acontece se o modelo pedir `tenant_id` nos argumentos?** `extra="forbid"` rejeita a chamada antes de qualquer acesso a dados.
4. **Porque é que a ferramenta mutável só propõe?** Separar proposta de efeito permite aprovação, idempotência e auditoria sem confiar no agente.
5. **A detecção de injecção resolve o problema?** Não. É visibilidade para o revisor. A protecção é estrutural: nenhuma acção mutável sem aprovação.
