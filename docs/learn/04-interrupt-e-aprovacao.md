# 04 — Interrupt, aprovação humana e retoma

## O problema

Um agente que pode alterar contas reais não pode decidir sozinho. A aprovação tem de ser (1) obrigatória antes de qualquer efeito, (2) feita por alguém autorizado e diferente do requester, (3) auditável, e (4) retomável: a tarefa pode esperar horas, e a API ou o worker podem reiniciar entretanto.

## O que entra e o que sai

Entra uma proposta mutável de um agente (por exemplo `reset_mfa` para `joao@nimbo`). Sai uma linha em `approvals` com estado `pending`, um evento `approval_requested`, uma pausa do grafo, e — depois da decisão — a retoma com `Command(resume=decision)`.

Excerto real de uma aprovação (tarefa de reset de MFA, sem crash):

```text
checkpoint next: ('approval_gate',) | pending: reset_mfa {'user_id': 'joao@nimbo'}
approval: apr-db449cfe28bab999125e3484 pending mutating_action+conflicting_evidence
resume: resumed
resume again: not_waiting
joao mfa_reset_count: 1 | effects: 1
audit: requested ines@nimbo {'reason': 'mutating_action', 'action': 'reset_mfa'}
audit: reason_added system {'reason': 'conflicting_evidence'}
audit: decided rui@nimbo {'decision': 'approve', 'comment': ''}
```

Repare no motivo `mutating_action+conflicting_evidence`: os dois procedimentos de MFA dão instruções opostas, e o verificador acrescentou esse motivo à aprovação já existente.

## Como funciona por dentro

1. **Criação da aprovação** (`agent_node.py`): quando a ferramenta mutável devolve uma proposta, `create_or_get` (`backend/app/store/approvals.py`) grava a aprovação. O id é derivado de `(task_id, kind, action, params)` (`approval_id_for`). Se o nó for reexecutado, encontra a mesma linha e não cria outra.
2. **Verificação** (`make_verifier`, `control_nodes.py`): acrescenta motivos (`conflicting_evidence`, `suspected_injection`) à aprovação pendente.
3. **Porta de aprovação** (`make_approval_gate`): chama `interrupt(payload)` com a proposta. O LangGraph pausa o grafo e o `invoke` devolve `__interrupt__`. A tarefa passa a `awaiting_approval` (`persist_outcome`, `service.py`).
4. **Decisão** (`resolve_approval`, `service.py`): só revisores (`reviewer`/`admin`) do mesmo tenant. Um requester recebe `ApprovalForbidden` (403 na API), mesmo que seja o autor. Outro tenant recebe `ApprovalNotFound` (404). A decisão grava `decided_by`, `decided_at` e comentário, e acrescenta um registo de auditoria.
5. **Retoma** (`resume_task_job`, `jobs.py`): lê a decisão **da base de dados**, não da mensagem da fila, e invoca `Command(resume=...)`.
6. **Ramos**: `reject` → `finalize` com `rejected`, sem efeito; `approve` ou `edit` → `execute_action` (se houver acção) ou `finalize`.

### Porque o nó reexecuta: o interrupt re-executa o nó

Este é o ponto que mais costuma surpreender. Quando o grafo retoma, o LangGraph **reexecuta o nó que chamou `interrupt()` desde o início**. `interrupt()` devolve então o valor de retoma em vez de pausar. Por isso `approval_gate` não tem efeitos antes do `interrupt`, e a criação da aprovação acontece no nó do agente (com id determinístico), não ali.

Este comportamento está demonstrado por teste: `tests/test_interrupt_reexecution.py::test_side_effect_before_interrupt_repeats_on_resume` mostra que um efeito colocado antes do `interrupt` corre duas vezes (`counter == 2`), e `test_node_with_interrupt_runs_again_on_resume` mostra que o nó corre de novo ao retomar.

## Porquê esta escolha

- **Aprovação como nó do grafo**, e não como estado externo: a pausa, a retoma e o histórico ficam no checkpoint.
- **Decisão lida da base de dados**: uma entrega duplicada da retoma não consegue inventar uma decisão.
- **Auditoria só de inserção** (`approval_audit`): o repositório não tem métodos de actualização nem de remoção para esta tabela. A edição de parâmetros fica registada com o valor original e o editado.

## Alternativas

- **Aprovação síncrona com espera bloqueante**: prende um worker por horas. Rejeitada.
- **Aprovação fora do grafo, com estado manual**: duplica o estado do checkpoint e perde a retoma automática.
- **Permitir que o requester aprove a própria acção**: rejeitada pela spec; é o caso que a separação de papéis existe para impedir.

## Como falha (e onde está testado)

| Caso | Teste |
|---|---|
| Requester tenta aprovar (403) | `test_requester_cannot_resolve_even_own_approval` |
| Revisor de outro tenant (404) | `test_reviewer_from_other_tenant_gets_not_found` |
| Resolução duplicada não altera nada | `test_second_resolution_is_idempotent_and_audited` |
| Edição regista original e editado | `test_edit_records_original_and_edited_values` |
| Edição fora do intervalo recusada | `test_edit_validation_rejects_out_of_range_days` |
| Rejeição não executa efeito | `test_rejection_path_leaves_no_effect` |
| Procedimento contraditório pausa para revisão | `tests/test_graph_flows.py::test_conflicting_procedures_pause_for_review` |
| Ticket malicioso exige aprovação, sem efeito | `tests/test_graph_flows.py::test_injected_ticket_pauses_for_approval_and_has_no_effect` |

## Perguntas de entrevista

1. **O que acontece se a API reiniciar com uma aprovação pendente?** A aprovação está na base de dados e o checkpoint está na base de dados; `GET /approvals` (grupo 7) continua a mostrá-la.
2. **Porque é que `approval_gate` não cria a aprovação?** Porque o nó é reexecutado ao retomar. A criação é idempotente, mas a pausa deve ser o único efeito do nó.
3. **Porque é que a retoma não leva a decisão na mensagem?** Para que a decisão só possa vir da base de dados, onde ficou auditada.
4. **Porque é que o requester não pode aprovar a própria acção?** Porque a aprovação existe para haver um segundo par de olhos. Permitir o contrário anula o controlo.
