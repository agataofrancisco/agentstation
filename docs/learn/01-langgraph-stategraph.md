# 01 — LangGraph StateGraph: estado, nós e arestas

## O problema

Um fluxo de agentes é uma sequência de decisões com estado partilhado. Escrever isso como um `while` com variáveis globais torna difícil saber em que passo se está, o que foi feito, e como retomar depois de uma falha. O `StateGraph` do LangGraph força três coisas: um **estado tipado**, **nós** que devolvem apenas as partes que mudam, e **arestas** explícitas (fixas ou condicionais).

## O que entra e o que sai

Entra um estado inicial (`TaskState`, em `backend/app/graph/state.py`) criado a partir da tarefa e da identidade do requester (`backend/app/service.py`, `initial_state`). Sai o estado final, com `status`, `results` e contadores.

Excerto real de uma execução (pedido de 3 subtarefas, provider `fake`), na ordem em que o LangGraph chamou os nós:

```text
task_queued None {'requester': 'ines@nimbo'}
node_started supervisor {}
delegation supervisor {'to': 'triage', 'provider': 'fake'}
node_started triage {}
llm_call triage {'provider': 'fake', 'tokens': 63, 'cost_usd': 0.001}
tool_call triage {'agent': 'triage', 'tool': 'get_ticket', 'status': 'ok', 'mutating': False, 'duration_ms': 5.281}
llm_call triage {'provider': 'fake', 'tokens': 137, 'cost_usd': 0.001}
node_finished triage {}
node_started supervisor {}
delegation supervisor {'to': 'knowledge_retrieval', 'provider': 'fake'}
node_started knowledge_retrieval {}
tool_call knowledge_retrieval {'agent': 'knowledge_retrieval', 'tool': 'search_procedures', 'status': 'ok', 'mutating': False, 'duration_ms': 10.641}
node_finished knowledge_retrieval {}
node_started supervisor {}
delegation supervisor {'to': 'reporting', 'provider': 'fake'}
node_started reporting {}
tool_call reporting {'agent': 'reporting', 'tool': 'draft_reply', 'status': 'ok', 'mutating': False, 'duration_ms': 5.571}
node_finished reporting {}
node_started supervisor {}
delegation supervisor {'to': 'verifier', 'provider': 'fake'}
node_started verifier {}
verifier verifier {'verdict': 'ok', 'reasons': []}
node_started finalize {}
task_finished finalize {'status': 'completed', 'limit_reason': None}
```

(Excerto truncado: foram omitidas algumas linhas `node_finished` e `llm_call`.)

## Como funciona por dentro

- **Estado**: `TaskState` é um `TypedDict` (`backend/app/graph/state.py`). O LangGraph aplica a cada nó um *merge* das chaves devolvidas. Por isso os nós devolvem dicionários parciais, e não o estado completo.
- **Construção**: `build_graph` (`backend/app/graph/build.py`) regista os nós com `add_node`, liga `START` ao `supervisor` com `add_edge`, e usa `add_conditional_edges` para o encaminhamento que depende do estado (`state["next"]`).
- **Envolvimento dos nós**: `traced` (`backend/app/graph/runtime.py`) envolve cada nó para gravar `node_started`/`node_finished` com duração. Não apanha excepções, porque `GraphInterrupt` (usado na aprovação, grupo 5) tem de atravessar o envolvimento.
- **Compilação**: `builder.compile(checkpointer=...)` liga o checkpointer. Sem ele não há `interrupt` nem retoma.

## Porquê esta escolha

- Os nós são pequenos e o grafo cabe num quadro branco: 8 nós e 3 pontos de decisão.
- Estado tipado + nós que devolvem diferenças tornam cada passo testável isoladamente (ver `tests/test_graph_flows.py`).
- Encaminhamento condicional lê uma chave do estado, nunca texto livre do modelo.

## Alternativas

- **Cadeia linear fixa** (a baseline do grupo 9): mais simples, mas não suporta a delegação dinâmica nem a aprovação intermédia de forma limpa.
- **Agentes que conversam livremente** (swarm): mais difíceis de limitar e de auditar.
- **Celery com chamadas encadeadas**: a fila passa a ser o estado. Rejeitada no D2 do design.

## Como falha (e onde está testado)

- Ciclo entre nós → `max_iterations` (`test_infinite_cycle_stops_at_max_iterations`).
- Rota inválida devolvida pelo supervisor → `route_rejected` e `failed` (ver `ALLOWED_ROUTES` em `control_nodes.py`).
- Chave de estado em falta quando um nó devolve algo não declarado: o LangGraph rejeita na compilação/execução; por isso `effect_result` foi acrescentado ao `TaskState`.

## Perguntas de entrevista

1. **Porque é que os nós devolvem diferenças e não o estado completo?** Porque o LangGraph faz o *merge* e o checkpoint guarda o estado resultante; devolver tudo aumenta o risco de sobrescrever chaves alheias.
2. **Como se garante que o encaminhamento não depende do LLM livre?** O supervisor devolve `next` que é validado contra `ALLOWED_ROUTES`; qualquer outro valor termina em `failed`.
3. **Para que serve `recursion_limit`?** É a segunda barreira do LangGraph; o nosso limite lógico (`max_iterations`) dispara antes. O valor é `max_iterations * 4 + 20` (`recursion_limit_for`).
4. **Porque é que o `traced` não apanha excepções?** `GraphInterrupt` é o mecanismo de pausa; apanhá-lo impediria a aprovação.
