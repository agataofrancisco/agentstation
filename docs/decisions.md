# Decisões

## Decisões do plano (confirmadas na implementação)

- D1 LangGraph StateGraph com supervisor e encaminhamento por `Literal` validado.
- D2 Checkpointer oficial; thread = `task_id`; PostgreSQL testado com `pgserver`.
- D3 Celery só como motor; `acks_late`; a retoma lê a decisão da base de dados.
- D4 `approval_gate` sem efeitos; efeito em `execute_action` com chave de idempotência.
- D5 Ferramentas com schemas e registo por agente.
- D6 Memória ChromaDB por tenant, filtro de escrita, TTL.
- D7 Limites no estado do grafo, verificados antes do LLM.
- D8 JWT demo por persona (sem palavra-passe; só com `DEMO_MODE`).
- D9 Baseline determinística (mesmos cenários).
- D10 Documentação pedagógica em `docs/learn/`.

## Decisões novas (tomadas pelo executor, por não estarem no plano)

1. **Login demo sem palavra-passe**, activo apenas com `DEMO_MODE=true`.
2. **Tabela `approval_audit`** (só inserção) e `worker_heartbeats`, além das tabelas listadas na proposta.
3. **Ferramentas por agente**: `triage` tem `propose_account_action` e `propose_ticket_status`; `reporting` não (o exemplo de `tool_not_allowed` da spec).
4. **Verificador sem LLM**: regras determinísticas para evidência, estados e aprovações. Rejeição de evidência termina em `needs_review` (a spec permitia voltar ao supervisor ou terminar).
5. **Conflito de procedimentos** cria uma aprovação do tipo `review`; quando há também uma acção mutável, os motivos são acumulados na mesma aprovação.
6. **Efeito falhado** (`not_found`) fica registado como `failed` para auditoria.
7. **Memória**: `memory_enabled` no utilizador (sem endpoint de activação; só seed). Resumo de memória usa ids e categorias, não o corpo dos tickets.
8. **Embeddings por hashing de bigramas** para a memória (sem rede). Aproximação de demonstração; qualidade não medida.
9. **Provider OpenAI-compatível** implementado e testado com servidor HTTP falso; nunca testado contra a API real (sem chave).
10. **Marcadores de teste** no pedido (`[loop]`, `[misuse]`, ...) só são interpretados pelo provider falso.
11. **Saúde**: em modo `CELERY_EAGER` o worker aparece como `eager`, não como `ok`.
12. **Heartbeat de worker** gravado na base de dados (sem broadcast de broker).
13. **Campo `crash_at_node`** nas definições: gancho só para testes de recuperação.
14. **Métricas** com estimativa de custo `chamadas × preço fixo` no provider falso, marcadas como estimativa.
