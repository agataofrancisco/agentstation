# Tasks

## 1. Fundações

- [x] 1.1 Criar a estrutura `backend/app/{api,graph,agents,tools,memory,auth,store,workers}`, `frontend/`, `migrations/`, `eval/`, `data/demo/` e `docs/learn/`; verificar com `git status`
- [x] 1.2 Confirmar na documentação oficial e fixar versões (FastAPI, Pydantic v2, LangGraph + checkpointer Postgres, SQLAlchemy, Alembic, Celery, redis, chromadb, httpx, pytest, Ruff); verificar a instalação num venv limpo
- [x] 1.3 Implementar `Settings`, `.env.example`, `/health` mínimo, Ruff e pytest; verificar que `ruff check` e `pytest` passam
- [x] 1.4 Escrever `docs/learn/00-visao-geral.md` com o diagrama Mermaid do grafo e dos processos (API, worker, DB, fila); verificar que corresponde à estrutura criada

## 2. Dados, autenticação e auditoria

- [x] 2.1 Criar modelos e migrações (`tasks`, `task_events`, `approvals`, `effects`, `tickets`, `procedures`, `users`); verificar com `alembic upgrade head` em SQLite e um teste de criação
- [x] 2.2 Implementar JWT demo com papéis e escopo por tenant; verificar com testes de 401, 403 e 404 cross-tenant
- [x] 2.3 Criar o seed sintético (2 tenants, ≥30 tickets, ≥15 procedimentos incluindo um contraditório e um ticket malicioso); verificar que o comando de seed é idempotente

## 3. Ferramentas

- [ ] 3.1 Implementar o registo de ferramentas, os schemas e o executor (validação → autorização → execução → evento); verificar com testes de `unknown_tool`, argumentos inválidos e `tool_not_allowed`
- [ ] 3.2 Implementar as 6 ferramentas sobre os dados demo e o sistema de efeitos simulado; verificar com testes de not_found cross-tenant e registo de efeito
- [ ] 3.3 Escrever `docs/learn/06-ferramentas-e-autorizacao.md`; verificar que cada regra citada tem um teste

## 4. Grafo e orquestração

- [ ] 4.1 Implementar o provider LLM (compatível com OpenAI, timeout/retries) e o provider falso determinístico com respostas por cenário; verificar com testes com servidor HTTP falso
- [ ] 4.2 Implementar o estado do grafo, os nós `supervisor`, `triage`, `knowledge_retrieval` e `reporting` e o encaminhamento estruturado; verificar com teste do pedido de 3 subtarefas em modo fake
- [ ] 4.3 Implementar o nó `verifier` e as guardas de limites (iterações, ferramentas, tempo, tokens, custo); verificar com testes de resposta sem evidência e de ciclo infinito → `limit_exceeded`
- [ ] 4.4 Implementar a detecção `suspected_injection` e a garantia de que não salta aprovação; verificar com o cenário do ticket malicioso
- [ ] 4.5 Escrever `docs/learn/01-langgraph-stategraph.md`, `02-supervisor-e-agentes.md` e `08-limites-e-custos.md`; verificar que os exemplos de estado vêm de uma execução real

## 5. Durabilidade, aprovação e idempotência

- [ ] 5.1 Ligar o checkpointer (memória/SQLite nos testes, Postgres configurável) com `thread_id = task_id`; verificar com teste de inspecção do checkpoint a meio
- [ ] 5.2 Implementar `approval_gate` com `interrupt`, a persistência da aprovação e a retoma com `Command(resume=...)` (aprovar, rejeitar, editar); verificar com testes dos três caminhos e 403 para requester
- [ ] 5.3 Implementar `execute_action` com a tabela `effects` e a reconciliação `effect_pending`; verificar com testes de resolução duplicada e reexecução do nó → `duplicate_effect_prevented`
- [ ] 5.4 Implementar os workers Celery (`run_task`, `resume_task`, `acks_late`) e o teste de crash (terminar o processo a meio e retomar); verificar com `pytest -m postgres` quando houver Postgres, ou registar a pendência
- [ ] 5.5 Escrever `docs/learn/03-checkpoints-e-durabilidade.md`, `04-interrupt-e-aprovacao.md` e `05-idempotencia-exactly-once.md`; verificar que a explicação da reexecução do nó tem um teste que a demonstra

## 6. Memória

- [ ] 6.1 Implementar a memória Chroma por tenant/utilizador com opt-in, TTL e o filtro de escrita (segredos/PII); verificar com testes de memória desligada, isolamento, password bloqueada e expiração
- [ ] 6.2 Expor `GET /memory` e `DELETE /memory/{id}` e mostrar as memórias recordadas por tarefa; verificar com teste de eliminação
- [ ] 6.3 Escrever `docs/learn/07-memoria.md`; verificar que os riscos descritos têm testes

## 7. API e eventos

- [ ] 7.1 Implementar `POST /tasks`, `GET /tasks/{id}`, `GET /approvals` e `POST /approvals/{id}/resolve` com escopo por papel; verificar com testes de API
- [ ] 7.2 Implementar o SSE `GET /tasks/{id}/events` com `Last-Event-ID`; verificar com teste de reconexão sem duplicados
- [ ] 7.3 Implementar `/metrics` (admin) e o `/health` completo (DB, fila, worker); verificar com teste de worker em baixo → `degraded`

## 8. Frontend

- [ ] 8.1 Criar a app React com login por persona, lista de tarefas e criação de pedido; verificar com `npm run build`
- [ ] 8.2 Implementar o diagrama do grafo com nó actual e a linha temporal por SSE; verificar no browser com uma tarefa de 3 subtarefas
- [ ] 8.3 Implementar a fila de aprovações (aceitar, rejeitar, editar), o painel de memória e a exportação; verificar no browser os fluxos de aprovação e de rejeição

## 9. Avaliação

- [ ] 9.1 Implementar a suite dos 7 cenários de demonstração com exit ≠ 0 em falha; verificar que passa em modo fake
- [ ] 9.2 Implementar a baseline determinística e o runner comparativo com as métricas da spec; verificar que o relatório inclui os cenários em que a baseline ganha
- [ ] 9.3 Correr a avaliação e gravar os resultados reais com metadados; verificar que os campos não medidos estão como `TODO: medir`
- [ ] 9.4 Escrever `docs/learn/09-multiagente-vs-workflow.md` com base nos resultados obtidos; verificar que cada conclusão cita um número do relatório

## 10. Entrega e integração

- [ ] 10.1 Escrever Dockerfiles e `docker-compose.yml` (api, worker, postgres, redis, frontend) marcados como não testados localmente; verificar com `docker compose config` quando houver Docker
- [ ] 10.2 Criar CI (Ruff, pytest, testes postgres/redis com services, cenários fake, build do frontend); verificar que o workflow é válido
- [ ] 10.3 Escrever `README.md`, `docs/architecture.md`, `docs/decisions.md` e `docs/case-study.md`; verificar que os comandos do README correm
- [ ] 10.4 Escrever `docs/learn/10-perguntas-de-entrevista.md` (≥25 perguntas); verificar a consistência com o código final
- [ ] 10.5 Revisão independente de segurança (autorização, aprovação, injecção, memória); verificar que os achados estão resolvidos ou documentados

## Workflow follow-up

- Suite real opcional com um modelo barato; gravar a demo em vídeo.
- Arquivar a change após revisão.
