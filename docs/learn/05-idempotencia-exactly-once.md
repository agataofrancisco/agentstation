# 05 — Idempotência e "exactly once"

## O problema

Uma acção aprovada tem de acontecer **no máximo uma vez**. Mas há três fontes de repetição: o nó pode ser reexecutado ao retomar (ver 04), a mesma decisão pode ser enviada duas vezes, e a entrega da retoma pode ser duplicada pela fila. Sem uma chave de idempotência, cada uma destas fontes pode aplicar o efeito de novo — por exemplo, um segundo reset de MFA.

## O que entra e o que sai

Entra a aprovação, os parâmetros (originais ou editados) e os identificadores da tarefa. Sai o resultado do efeito e um estado: `executed` (criado agora), `duplicate` (já tinha sido feito) ou `reconciled` (estava pendente de um crash e foi concluído).

Excerto real de um caso de reexecução (teste `test_reexecuting_execute_node_prevents_duplicate_effect`): o nó `execute_action` é corrido duas vezes com o mesmo estado, como acontece depois de um crash.

```text
first  -> effect_executed  (mfa_reset_count = 1)
second -> duplicate_effect_prevented
effect rows: 1
```

## Como funciona por dentro

**Chave**: `idempotency_key(task_id, approval_id, action, params)` (`backend/app/tools/effects.py`) é o SHA-256 de uma representação canónica (JSON com chaves ordenadas e parâmetros normalizados). Mudar um parâmetro muda a chave; repetir a mesma aprovação não.

**Duas fases**:

1. **Fase 1 — intenção**: `INSERT` de uma linha `effect_pending` com `idempotency_key UNIQUE`, seguido de `commit`. Se o `INSERT` falhar por chave duplicada (`IntegrityError`), outra execução já chegou lá: reexecuta-se a função e cai nos casos seguintes.
2. **Fase 2 — efeito**: uma **única transacção** que altera os dados e marca a linha como `done` com o resultado. Ou tudo, ou nada.

**Casos**:

- Linha `done` → devolve o resultado guardado, estado `duplicate`.
- Linha `effect_pending` sem `done` → a fase 2 é executada agora, estado `reconciled`. Isto cobre o crash entre as duas fases.
- Sem linha → fase 1 e depois fase 2, estado `executed`.
- Erro de negócio (`not_found`) → a linha passa a `failed` e o erro sobe. Fica um registo de auditoria.

**Reconciliação na arranque**: `reconcile_pending` percorre as linhas `effect_pending` e refaz o efeito. Só é seguro porque o sistema simulado é atómico (fase 2 numa transacção). Para um sistema externo real, isto não chega (ver limitações).

## Porquê esta escolha

- **Chave derivada do conteúdo**, e não um UUID aleatório: a mesma aprovação com os mesmos parâmetros produz sempre a mesma chave, mesmo depois de um crash.
- **Intenção gravada antes do efeito**: se o processo morrer, a intenção fica registada e pode ser reconciliada. Sem isto, não se distingue "nunca tentou" de "tentou e morreu".
- **Efeito e marca `done` na mesma transacção**: no sistema simulado, não há janela entre o efeito e a marca.

## Alternativas

- **Exactly once verdadeiro**: não existe em sistemas distribuídos sem cooperação do destino. O que se consegue é "at-most-once por chave" no nosso lado, mais reconciliação; o destino externo tem de aceitar a mesma chave para fechar a janela.
- **Marcar `done` antes do efeito** (at-most-once puro): se o processo morrer antes do efeito, a acção nunca acontece, o que é pior para um reset de MFA aprovado.
- **Lock distribuído**: resolve concorrência, não repetição; a chave UNIQUE já dá a exclusão necessária.

## Limitações honestas

- **Janela externa**: com um sistema real (ex.: API de identidade), o efeito pode ocorrer no destino e o processo morrer antes de gravar `done`. Na reconciliação, a acção seria repetida sem a chave ser aceite pelo destino. Mitigação correcta: enviar a `idempotency_key` ao destino e consultar o estado antes de repetir. **Não implementado** — o sistema é simulado e não há integrações reais (fora de âmbito).
- O estado `failed` não é reconciliado automaticamente.

## Como falha (e onde está testado)

| Caso | Teste |
|---|---|
| Mesma chave duas vezes → uma linha, uma alteração | `tests/test_tools_handlers.py::test_effect_is_applied_once_for_same_key` |
| Chave depende de aprovação e parâmetros, não de espaços | `test_effect_key_depends_on_approval_and_params` |
| Reexecução do nó → `duplicate_effect_prevented` | `tests/test_approvals_and_jobs.py::test_reexecuting_execute_node_prevents_duplicate_effect` |
| Intenção pendente após crash → `reconciled` uma vez | `test_pending_effect_is_reconciled_once` |
| Resolução duplicada não repete a acção | `test_full_approve_path_through_jobs_executes_once` |
| Efeito sobre outro tenant falha sem alterar dados | `test_effect_on_other_tenant_fails_without_side_effect` |

## Perguntas de entrevista

1. **O que é "exactly once" e porque é difícil?** Requer cooperação do destino: sem a chave aceite do outro lado, uma falha entre o efeito e o registo deixa ambiguidade.
2. **Porque é que a chave é um hash e não um UUID?** Para ser reproduzível após um crash, sem guardar estado adicional.
3. **Porque gravar a intenção antes?** Para distinguir "nunca tentou" de "tentou e não sabemos se aplicou".
4. **O que falta para isto ser seguro com um sistema externo?** Enviar a chave ao destino e consultar o estado antes de repetir (ver limitações).
