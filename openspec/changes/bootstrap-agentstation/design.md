# Design

## Context

O repositório está vazio. Motivação: ver `proposal.md`. Requisitos: ver `specs/`. O ambiente local não tem Docker, por isso Postgres e Redis reais ou são instalados nativamente ou ficam para CI/cloud. Objectivo pedagógico: o grafo tem de ser pequeno o suficiente para ser desenhado e explicado num quadro branco.

## Goals / Non-Goals

**Goals:**
- Um grafo LangGraph explícito, com poucos nós e transições legíveis.
- Separação clara entre **estado do grafo** (checkpointer durável), **trabalho assíncrono** (Celery) e **dados da aplicação** (Postgres).
- Efeitos externos isolados atrás de aprovação e idempotência.

**Non-Goals:**
- Agentes autónomos de longo prazo, planeamento aberto e auto-geração de ferramentas.
- Integrações reais com sistemas de tickets ou de identidade.

## Decisions

### D1 — LangGraph `StateGraph` com supervisor
Os nós são `supervisor`, `triage`, `knowledge_retrieval`, `reporting`, `verifier`, `approval_gate`, `execute_action` e `finalize`. O supervisor decide o próximo nó com output estruturado (`next: Literal[...]`). Não há texto livre a decidir o fluxo.
- *Alternativa:* uma cadeia linear fixa. É mais simples e é precisamente a baseline (D9).
- *Alternativa:* agentes "swarm" que falam livremente uns com os outros. Rejeitada porque é mais difícil limitar e auditar.

### D2 — Checkpointer Postgres oficial do LangGraph
`thread_id = task_id`. Em testes rápidos usa-se o checkpointer em memória/SQLite. Os testes de recuperação real exigem Postgres e estão marcados `@pytest.mark.postgres`. A API exacta (`PostgresSaver`, `interrupt`, `Command`) é confirmada na documentação actual antes de implementar.
- *Porquê não Redis/Celery para o estado:* uma fila entrega mensagens e não guarda um histórico consistente de estado. Perder o broker não pode fazer perder a tarefa.

### D3 — Celery só como motor de execução
`POST /tasks` cria a linha na base de dados e enfileira `run_task(task_id)`. O worker invoca o grafo com o `thread_id`. A retoma depois de aprovação enfileira `resume_task(task_id, decision)`. Se o worker morrer, o job é reentregue (`acks_late`) e o grafo retoma a partir do checkpoint.

### D4 — Interrupção e idempotência
`approval_gate` chama `interrupt(payload)`. A resolução gera `Command(resume=decision)`. **Atenção:** o nó que contém `interrupt` reexecuta desde o início ao retomar. Por isso, o nó `approval_gate` não tem efeitos, e o efeito fica num nó separado (`execute_action`), que primeiro verifica a tabela `effects(idempotency_key UNIQUE)`. A chave é `sha256(task_id, approval_id, action, params_normalizados)`. Fazer o INSERT antes do efeito garante "no máximo uma vez".
- *Trade-off:* "no máximo uma vez" pode deixar um efeito por executar se o processo morrer entre o INSERT e o efeito. Mitigação: o estado `effect_pending` é reconciliado no arranque. Este é um bom tema de entrevista sobre exactly-once.

### D5 — Ferramentas
Usam schemas Pydantic e um registo por agente (`AGENT_TOOLS = {"triage": [...], ...}`). Um executor central faz validação → autorização com a identidade da tarefa, não com o que o modelo diz → execução → evento. O output das ferramentas volta ao modelo delimitado como dado.

### D6 — Memória
ChromaDB com uma colecção por tenant e filtro por `user_id`. Antes de escrever, passa por um filtro de regras (regex de segredos e PII, origem não confiável). Expiração com TTL guardado em metadado e filtrada na leitura. Um job periódico faz a limpeza.

### D7 — Limites
O estado do grafo tem contadores (`iterations`, `tool_calls`, `tokens`, `cost_usd`, `started_at`). Uma guarda antes de cada nó LLM termina em `limit_exceeded`. O LangGraph tem também `recursion_limit` como segunda barreira.

### D8 — Autenticação e frontend
JWT demo com papéis (como no GroundVault). O frontend é React (Vite) com React Flow para o diagrama do grafo e EventSource para o SSE.

### D9 — Baseline determinística
É um pipeline fixo: regras de palavras-chave → pesquisa de procedimento → template de resposta → pedido de aprovação se a acção for mutável. Corre os mesmos cenários e mede o mesmo. Hipótese a testar, não assumida: a baseline ganha em latência e custo nos pedidos simples, e perde em pedidos compostos ou ambíguos.

### D10 — Documentação pedagógica
`docs/learn/` tem: `00-visao-geral`, `01-langgraph-stategraph`, `02-supervisor-e-agentes`, `03-checkpoints-e-durabilidade`, `04-interrupt-e-aprovacao`, `05-idempotencia-exactly-once`, `06-ferramentas-e-autorizacao`, `07-memoria`, `08-limites-e-custos`, `09-multiagente-vs-workflow`, `10-perguntas-de-entrevista`. Todos seguem a estrutura problema → entrada/saída → por dentro → porquê → alternativas → falhas → perguntas.

## Risks / Trade-offs

- [A API do LangGraph muda entre versões] → Versão fixada e testes de contrato sobre `interrupt`/`Command`/checkpointer.
- [Sem Docker, não há Postgres nem Redis locais] → Instalação nativa opcional, fakes nos testes unitários e testes marcados `postgres`/`redis` em CI com services.
- [O provider falso torna o fluxo artificialmente fiável] → As métricas fake ficam identificadas; uma suite real opcional usa um modelo barato.
- [Multi-agente acrescenta latência e custo] → Medido contra a baseline e reportado sem esconder.
- [A janela entre o registo de idempotência e o efeito] → Estado `effect_pending` com reconciliação e documentado.

## Migration Plan

Projecto novo. Migrações Alembic para as tabelas da aplicação; o checkpointer cria as suas tabelas com `setup()`. Deploy documentado: API + worker num serviço de containers, com Postgres e Redis geridos.

## Open Questions

- Que modelo barato usar na suite real? Não altera o desenho.
