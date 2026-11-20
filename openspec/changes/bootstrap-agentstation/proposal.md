# Proposal

## Why

As equipas de helpdesk de TI passam o dia a fazer triagem de tickets, a procurar procedimentos e a escrever respostas. Também executam acções sensíveis, como reset de MFA, alteração de permissões ou desactivação de contas. Um agente LLM pode acelerar este trabalho, mas um agente que **age sozinho** sobre contas reais é um risco inaceitável. O AgentStation mostra três coisas: orquestração multi-agente com estado durável, aprovação humana obrigatória antes de qualquer efeito externo e execução que sobrevive a crashes sem repetir acções. Mostra também, com medição, quando é que um workflow determinístico simples teria sido melhor.

Domínio fictício: o helpdesk interno da **Nimbo Software** (tenant `nimbo`), com os papéis `requester`, `reviewer` e `admin`. Há um segundo tenant, **Atlas Retalho** (`atlas`), para provar o isolamento. Todos os tickets, utilizadores e procedimentos são sintéticos.

## What Changes

- Projecto novo em `projects/agentstation`: backend FastAPI + LangGraph, workers Celery, Postgres, Redis, ChromaDB e frontend React.
- Um supervisor decompõe pedidos e delega em 3 agentes especializados (`triage`, `knowledge_retrieval`, `reporting`). Um nó `verifier` independente valida schemas, evidências e permissões.
- Execução durável com checkpoints em Postgres por thread. A execução retoma depois de reiniciar a API ou o worker.
- Ferramentas tipadas e numa allowlist (consultar tickets, consultar procedimentos, criar rascunho de resposta, propor mudança de estado, propor acção de conta). A autorização é verificada no backend e cada acção tem uma chave de idempotência.
- Aprovação humana com `interrupt()`/`Command(resume=...)` para qualquer acção que altere dados e para casos de risco ou de pouca evidência. Os pedidos de aprovação são persistidos e auditados.
- Memória de curto prazo (checkpoints) e memória longa semântica opt-in, separada por tenant e por utilizador, com origem, expiração e eliminação.
- Limites rígidos por tarefa: iterações, chamadas de ferramentas, tempo, tokens e custo.
- API `POST /tasks`, `GET /tasks/{id}`, `GET /tasks/{id}/events` (SSE), `GET /approvals`, `POST /approvals/{id}/resolve`, `GET /memory`, `DELETE /memory/{id}`, health e metrics.
- Uma comparação medida com uma baseline de workflow determinístico sobre os mesmos cenários.
- Documentação de aprendizagem em `docs/learn/`.

## Capabilities

### New Capabilities
- `agent-orchestration`: supervisor, agentes especializados, verificador, encaminhamento entre nós e limites de execução.
- `durable-execution`: checkpoints persistentes, retoma após falha e histórico de eventos da tarefa.
- `human-approval`: pedidos de aprovação, interrupção e retoma do grafo, decisões (aceitar, rejeitar, editar) e auditoria.
- `agent-tools`: registo de ferramentas, schemas, autorização, idempotência e defesa contra tool injection.
- `agent-memory`: memória semântica de longo prazo, com escopo, origem, expiração, visualização e eliminação.
- `task-interface`: API de tarefas, stream de eventos, autenticação por papéis e painel web.
- `agent-evaluation`: cenários de demonstração, métricas de execução e comparação com uma baseline determinística.

### Modified Capabilities
<!-- Nenhuma: projecto novo. -->

## Impact

- **Código novo**: `backend/` (API, grafo, ferramentas e workers), `frontend/`, `migrations/`, `eval/`, `data/demo/` e `docs/`.
- **Dependências** (versões confirmadas na documentação oficial ao implementar): FastAPI, Pydantic v2, LangGraph + o checkpointer Postgres oficial, SQLAlchemy/Alembic, Celery, Redis, ChromaDB, httpx, pytest e Ruff. React no frontend.
- **Infraestrutura**: precisa de Postgres e Redis. Sem Docker local, os testes usam SQLite/fakes onde a semântica o permite. O checkpointer Postgres e a recuperação após crash só são testados de verdade com Postgres real. Isso fica explícito nos relatórios.
- **Fora de âmbito**: integrações reais (Jira, Okta, email), envio real de mensagens e SSO.
