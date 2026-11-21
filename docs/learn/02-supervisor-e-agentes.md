# 02 — Supervisor e agentes especializados

## O problema

Um único agente com todas as ferramentas é difícil de limitar: qualquer instrução maliciosa ou erro de raciocínio tem acesso a tudo. Dividir em agentes com responsabilidades estreitas reduz a superfície, mas só funciona se alguém decidir a ordem e impedir que um agente use ferramentas de outro. Aqui essa decisão é do **supervisor**, e a restrição é do **registo de ferramentas**.

## O que entra e o que sai

Entra o pedido em texto livre. O supervisor recebe `request` e a lista `done` (agentes já concluídos) e devolve `{"next": ...}`. Cada agente recebe o pedido, os resultados anteriores (`results`) e as observações das ferramentas da sua chamada, e devolve `{"tool_calls": [...], "result": ...}`.

Os agentes e a sua allowlist são derivados do registo (`agent_tools()` em `backend/app/tools/registry.py`):

```text
triage:               get_ticket, propose_account_action, propose_ticket_status, search_tickets
knowledge_retrieval:  search_procedures, search_tickets
reporting:            draft_reply, get_ticket
```

## Como funciona por dentro

- **Supervisor** (`make_supervisor`, `backend/app/graph/control_nodes.py`): incrementa `iterations`, verifica limites, chama o LLM com saída JSON e valida `next` contra `ALLOWED_ROUTES`. Não tem ferramentas.
- **Agentes** (`make_agent_node`, `backend/app/graph/agent_node.py`): fazem até `MAX_AGENT_STEPS = 3` chamadas ao LLM. Cada chamada pode pedir ferramentas; o resultado de cada uma volta ao modelo como observação. Quando o modelo devolve `result` sem novas chamadas, o nó termina.
- **Verificador** (`_verdict`, `control_nodes.py`): determinístico, sem LLM. Rejeita a resposta se o `reporting` não citar nenhum procedimento recuperado pelo `knowledge_retrieval` (o caso `no_evidence`).

Excerto real do caso "resposta sem evidência" (`[no-evidence]`, provider `fake`):

```text
verifier verifier {'verdict': 'needs_review', 'reason': 'no_evidence'}
task_finished finalize {'status': 'needs_review', 'limit_reason': None}
```

## Porquê esta escolha

- **Supervisor com saída estruturada**: o fluxo é um conjunto fechado de rotas, por isso é auditável e testável.
- **Âmbito por agente**: `reporting` não consegue propor uma acção de conta, mesmo que o modelo tente (teste `test_wrong_tool_from_agent_is_refused_and_recorded`).
- **Verificação independente**: quem produz a resposta não a aprova.

## Alternativas

- **Swarm** (agentes que se passam o controlo entre si): difícil de limitar; rejeitada.
- **Um agente com ferramentas e prompt de papéis**: menos superfície de código, mas o âmbito deixa de ser garantido pelo sistema.
- **Verificador com LLM**: mais flexível, mas introduz outro modelo a confiar. Mantivemos regras determinísticas para a evidência e as permissões.

## Como falha (e onde está testado)

| Falha | Comportamento | Teste |
|---|---|---|
| Ferramenta fora do âmbito | `tool_not_allowed`, tarefa continua | `test_wrong_tool_from_agent_is_refused_and_recorded` |
| Ferramenta inexistente | `unknown_tool`, tarefa continua | `test_unknown_tool_is_refused_and_task_still_reaches_verdict` |
| Resposta sem evidência | `needs_review` | `test_response_without_citation_is_rejected_as_needs_review` |
| Ticket de outro tenant | triagem com erro → `needs_review`, sem dados | `test_cross_tenant_ticket_gives_needs_review_not_data` |
| LLM indisponível | `llm_error` no evento; nó sem resultado → verificador rejeita | cobertura parcial: `tests/test_llm_provider.py` |

## Perguntas de entrevista

1. **Porque o supervisor não tem ferramentas?** Para que a decisão de encaminhamento nunca possa ter efeitos externos.
2. **Como se impede o agente de usar uma ferramenta de outro?** O executor verifica `ctx.agent in spec.allowed_agents` antes de qualquer acesso a dados.
3. **Porque limitar a 3 chamadas por agente?** Limita custo e ciclos internos; o limite de iterações do grafo é a barreira global.
4. **Quando é que o multi-agente não compensa?** Mede-se no grupo 9: pedidos simples podem ser melhor servidos por um workflow determinístico.
