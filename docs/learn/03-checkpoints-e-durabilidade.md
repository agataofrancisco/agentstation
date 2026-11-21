# 03 — Checkpoints e durabilidade

## O problema

Uma tarefa de agentes pode demorar minutos e fazer várias chamadas caras. Se o worker morrer a meio, a solução ingénua é recomeçar do zero — o que repete chamadas ao LLM e, pior, pode repetir efeitos externos. A solução é guardar o estado do grafo **depois de cada passo** numa base de dados durável, e retomar do último passo guardado.

## O que entra e o que sai

Entra o estado inicial da tarefa (`initial_state`, `backend/app/service.py`). Sai um *checkpoint* por passo, indexado por `thread_id = task_id`. Ao retomar, o worker pergunta ao checkpointer qual é o próximo nó e que valores tem acumulados (`snapshot.next`, `snapshot.values`).

Excerto real, capturado com checkpointer SQLite numa tarefa que pausa para aprovação:

```text
run: started
checkpoint next: ('approval_gate',) | pending: reset_mfa {'user_id': 'joao@nimbo'}
```

O mesmo mecanismo, em PostgreSQL real, é exercitado pelo teste de recuperação (ver abaixo).

## Como funciona por dentro

- **Escolha do checkpointer**: `open_checkpointer` (`backend/app/graph/checkpointer.py`) devolve `PostgresSaver` para `postgresql://...` e `SqliteSaver` para `sqlite:///...`. O `PostgresSaver` cria as suas tabelas com `setup()`, que é idempotente.
- **Thread**: `graph_config` (`backend/app/service.py`) põe `thread_id = task_id`. Uma tarefa = um fio de estado.
- **Durabilidade síncrona**: `graph.invoke(..., durability="sync")` (`run_graph`). Sem isto, o checkpoint pode ser escrito de forma assíncrona e perder-se num crash. Este parâmetro é o que torna o teste de crash fiável.
- **Retoma**: `run_task_job` (`backend/app/workers/jobs.py`) lê o snapshot. Se houver checkpoint e não estiver à espera de aprovação, invoca o grafo com `None` (continua do `snapshot.next`). Se estiver à espera, não faz nada.
- **Estado no checkpoint, não na fila**: a mensagem Celery só leva `task_id`. Perder o broker não perde a tarefa.

## Porquê esta escolha

- O checkpoint é o estado de execução; a base de dados da aplicação guarda o estado de negócio (tarefa, eventos, aprovações). Separar as duas coisas evita um segundo modelo de estado.
- PostgreSQL real no teste: SQLite não reproduz as garantias de escrita concorrente de produção.

## Alternativas

- **Guardar o estado manualmente numa tabela JSON**: funciona, mas reimplementa o checkpointer e perde as garantias de `thread_id` e de histórico do LangGraph.
- **Estado na fila Celery** (resultados ou mensagens com o estado): perder o broker perde a tarefa. Rejeitada no D2.
- **`durability="async"`** (predefinido): mais rápido, mas o checkpoint pode não estar escrito quando o processo morre. Escolhemos `sync` porque a correção vale mais que a latência aqui.

## Como falha (e onde está testado)

- **Crash entre passos** (worker terminado depois de `triage`, antes de `knowledge_retrieval`): `tests/test_postgres_recovery.py::test_worker_crash_then_resume_does_not_repeat_triage`. O processo filho sai com código `137` a meio; outro processo inspeciona o checkpoint (`next == ('knowledge_retrieval',)`); depois a retoma num processo novo e a triagem **não** é recalculada (`get_ticket` continua com 1 chamada, `node_started triage` com 1 ocorrência). Passou com PostgreSQL 16.2 real via `pgserver`.
- **Retoma duplicada**: `test_full_approve_path_through_jobs_executes_once` (segunda retoma → `not_waiting`).
- **Checkpoint de aprovação pendente**: `test_sqlite_checkpoint_shows_pending_approval`.

## Limitações honestas

- O teste de crash mata um processo filho que executa `run_task_job` directamente, **não um worker Celery real**. O código Celery existe (`backend/app/workers/tasks.py`, `acks_late=True`) mas não foi arrancado com um broker vivo neste ambiente (sem Redis; o broker `filesystem://` não foi validado). Ver o relatório final.
- Não há reconciliação de checkpoints órfãos (tarefa `running` sem worker); fica para o `/health` e para o grupo 7.

## Perguntas de entrevista

1. **O que acontece se o worker morrer depois de executar um nó mas antes de o checkpoint ser escrito?** Esse nó é reexecutado. Por isso os nós com efeitos externos precisam de idempotência (ver 05).
2. **Porque é que `durability="sync"`?** Para o checkpoint estar escrito antes de o passo seguinte começar; `async` pode perder o último passo num crash.
3. **Porque não guardar o estado na fila?** A fila entrega mensagens, não guarda um histórico consistente. Perder o broker não pode perder a tarefa.
4. **Como se testa recuperação sem Docker?** Com `pgserver`, que arranca um PostgreSQL real, e um processo filho que termina com `os._exit`.
