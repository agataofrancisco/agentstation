# 08 — Limites de execução e custos

## O problema

Um agente que pode chamar um LLM em ciclo pode gastar tempo, tokens e dinheiro sem chegar a lado nenhum. Um limite só protege se for **verificado antes** de cada chamada cara, e se o motivo ficar registado para que o revisor perceba porque a tarefa parou.

## O que entra e o que sai

Entram os contadores acumulados no estado (`counters`: `iterations`, `llm_calls`, `tool_calls`, `tokens`, `cost_usd`) e o instante de início (`started_at`). Sai um motivo (`limit_reason`) ou `None`.

Os tectos vêm de `Settings` (`backend/app/config.py`): `max_iterations=12`, `max_tool_calls=20`, `max_seconds=120`, `max_tokens=50000`, `max_cost_usd=0.5`, todos configuráveis por variável de ambiente.

Excerto real de um orçamento de custo baixo (`max_cost_usd=0.0015`, custo fake de 0.001 por chamada), capturado pelo teste `test_cost_budget_stops_further_llm_calls`:

```text
llm_calls = 2   # 1 do supervisor + 1 da triagem
limit_reason = 'max_cost'   # supervisor, antes da 3.a chamada
```

## Como funciona por dentro

- `check_limits` (`backend/app/graph/limits.py`) é uma função pura. Recebe contadores, o instante actual e as definições, e devolve a primeira regra violada, pela ordem: iterações, ferramentas, tempo, tokens, custo.
- O **supervisor** incrementa `iterations` e verifica antes de decidir (`make_supervisor`). Se houver limite, a rota é `finalize` com `status = limit_exceeded`.
- Os **agentes** verificam antes de cada chamada ao LLM dentro do seu ciclo (`agent_node.py`). Se o limite for atingido, param sem chamar o modelo.
- A **segunda barreira** é o `recursion_limit` do LangGraph (`recursion_limit_for`, `build.py`), fixado acima do limite lógico para nunca disparar primeiro.
- O **custo** vem do provider: no cliente real, `tokens × preço por mil` (`llm.py`). No provider falso é um valor fixo configurável e está identificado como `provider: fake`.

## Porquê esta escolha

- **Verificar antes da chamada** e não depois: o custo que já foi feito não se recupera, mas a chamada seguinte pode ser evitada.
- **Contadores no estado do grafo**: sobrevivem a crashes porque fazem parte do checkpoint.
- **Motivo explícito**: `max_iterations` e `max_cost` aparecem em `task_finished` e na tarefa, e não como erro genérico.

## Alternativas

- **Timeout global no worker**: mata o processo mas não deixa estado nem motivo legível.
- **Orçamento por utilizador/dia**: útil em produção, fora do âmbito deste change.
- **Estimar tokens antes de chamar**: a contagem real vem da resposta do provider; a nossa estimativa no provider falso é `len(json)/4`, só para ter números.

## Como falha (e onde está testado)

- Ciclo infinito → `max_iterations` (`test_infinite_cycle_stops_at_max_iterations`).
- Orçamento de custo → `max_cost` e nenhuma chamada extra (`test_cost_budget_stops_further_llm_calls`).
- Limites aplicados a funções puras: ver regras em `check_limits`.

Números de custo e latência reais só existem no grupo 9 (`eval/`). Este documento não cita valores medidos.

## Perguntas de entrevista

1. **Porque verificar antes e não depois da chamada?** Porque o custo de uma chamada já feita é irreversível.
2. **Porque os contadores estão no estado do grafo?** Para sobreviverem à retoma depois de um crash e não serem reiniciados a zero.
3. **Qual é a diferença entre `max_iterations` e `recursion_limit`?** O primeiro é lógico e dá um motivo legível; o segundo é uma proteção do próprio LangGraph e termina com erro.
4. **Como se calcula o custo com um provider que não o informa?** Não se calcula: fica o valor configurável e marca-se como estimativa.
