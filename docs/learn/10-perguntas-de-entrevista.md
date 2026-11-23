# 10 — Perguntas de entrevista

Cada resposta aponta para o código ou para o documento onde o tema está explicado. Onde a resposta depende de algo não medido ou não implementado, diz-se.

## Orquestração e grafo

1. **Porque LangGraph e não um `while` com variáveis?** O estado é tipado, os nós devolvem diferenças, e o checkpointer guarda cada passo. Ver `01`.
2. **Como o supervisor decide o próximo nó?** Com saída `next` validada contra `ALLOWED_ROUTES` (`backend/app/graph/control_nodes.py`). Texto livre não decide o fluxo.
3. **Porque o supervisor não tem ferramentas?** Para que a decisão de encaminhamento nunca tenha efeitos externos. Ver `02`.
4. **Como limitas um agente às suas ferramentas?** `allowed_agents` no registo, verificado no executor antes de qualquer acesso a dados (`backend/app/tools/executor.py`).
5. **O que faz o verificador?** Regras determinísticas: resultados completos, citações dentro das evidências recuperadas, e motivos de aprovação. Não usa LLM.

## Durabilidade

6. **O que é um checkpoint e onde fica?** O estado do grafo por passo, indexado por `thread_id = task_id`, no PostgreSQL (ou SQLite em dev). Ver `03`.
7. **Porque `durability="sync"`?** Para o checkpoint estar escrito antes do passo seguinte. Com `async` o último passo pode perder-se num crash.
8. **Porque não guardar o estado na fila Celery?** A fila entrega mensagens, não guarda um histórico consistente. Perder o broker não pode perder a tarefa.
9. **Como testaste a recuperação após crash?** Um processo filho termina com `os._exit` em `knowledge_retrieval`; outro processo retoma do checkpoint; a triagem não é recalculada. Passou com PostgreSQL 16.2 real via `pgserver`.
10. **O que NÃO está provado sobre o Celery?** Não arrancámos um worker Celery vivo com broker. O código existe (`acks_late`), mas a recuperação foi testada com um processo filho que chama `run_task_job`. Fica como pendência.

## Aprovação

11. **Porque é que o nó de aprovação reexecuta ao retomar?** O LangGraph reexecuta o nó com `interrupt()` desde o início. Demonstrado por `tests/test_interrupt_reexecution.py`. Ver `04`.
12. **Porque a decisão vem da base de dados e não da mensagem?** Para que uma entrega duplicada não invente uma decisão, e para haver auditoria.
13. **Pode o requester aprovar a sua própria acção?** Não. `resolve_approval` exige revisor do mesmo tenant; a API devolve 403 (`tests/test_api_tasks.py`).
14. **Como funciona a edição antes de aprovar?** Os valores originais e editados ficam em `approval_audit`; a edição é validada (ex.: dias entre 1 e 365).

## Idempotência

15. **O que é "exactly once"?** Requer cooperação do destino. O que fazemos é idempotência por chave no nosso lado e reconciliação. Ver `05`.
16. **Como se deriva a chave?** SHA-256 de `(task_id, approval_id, action, params normalizados)`. Mudar um parâmetro muda a chave.
17. **Porque duas fases (intenção e efeito)?** Para distinguir "nunca tentou" de "tentou e não sabemos", e reconciliar na retoma.
18. **Qual é a limitação com um sistema externo?** A janela entre o efeito no destino e a marca `done`. A mitigação correcta é enviar a chave ao destino e consultar antes de repetir. Não implementado (sem integrações reais).

## Ferramentas e segurança

19. **Porque é que a autorização não está no prompt?** O prompt contém dados não confiáveis. A autorização lê a identidade do contexto de execução. Ver `06`.
20. **Porque `not_found` e não `403` para outro tenant?** Para não revelar a existência do recurso.
21. **Como tratas instruções escondidas num ticket?** Varrimento de padrões (`suspected_injection`), dados delimitados, e aprovação obrigatória para qualquer acção mutável. A detecção por padrões não é a defesa principal.
22. **O que acontece se o modelo pedir `tenant_id` nos argumentos?** `extra="forbid"` rejeita a chamada antes de qualquer acesso a dados.

## Memória

23. **Porque a memória é opt-in?** Privacidade e controlo. O flag está em `users.memory_enabled` e por omissão é `False`.
24. **Como impedes que uma memória envenenada persista?** Filtro à escrita (segredos, dados pessoais, origem com `suspected_injection`), que bloqueia e regista. Ver `07`.
25. **Como é garantido o isolamento?** Uma colecção ChromaDB por tenant, filtrada por utilizador e validade na própria consulta.

## Limites, custos e avaliação

26. **Porque verificar limites antes do LLM?** O custo de uma chamada já feita não se recupera. Ver `08`.
27. **Qual é a diferença entre `max_iterations` e `recursion_limit`?** O primeiro é lógico e dá um motivo legível; o segundo é a barreira do LangGraph.
28. **O multi-agente compensa?** Nos cenários medidos, a baseline é muito mais rápida e barata; a vantagem medida é a durabilidade e o efeito único. Ver `09`.
29. **Porque a baseline não é uma prova de superioridade?** Foi escrita com as mesmas regras dos cenários. É uma verificação de coerência.
30. **Que custo real tem o sistema?** Não medido. Só há custo estimado com preço fixo do provider falso. Latência e custo do LLM real: `TODO: medir`.

## Operação

31. **Como se verifica a saúde?** `/health` verifica a base de dados e um heartbeat de worker; sem worker activo, o estado é `degraded`.
32. **O que é o `Last-Event-ID` no SSE?** O cliente reconecta com o último `seq` recebido e recebe só os eventos seguintes, sem duplicados.
33. **Onde ficam as migrações e quem as aplica?** Alembic (`migrations/`); `create_all` só em testes e demos. O seed é idempotente (`merge` por chave).
34. **O que falta para produção?** Worker Celery vivo com broker, frontend, integrações reais, revisão de segurança independente, e medições com provider real.

Notas: a lista de decisões novas está em `docs/decisions.md`; as limitações de segurança estão em `docs/security-review.md`.
