# Caso de estudo

Um helpdesk interno precisa de triagem rápida, mas nenhuma acção sobre contas pode acontecer sem um revisor. O AgentStation mostra o padrão: supervisor com agentes de âmbito limitado, verificador independente, aprovação obrigatória, efeitos exactamente uma vez, e retoma após crash.

## Resultados medidos (provider fake, commit do relatório `eval/results/latest.json`)

- Os 7 cenários passam no multi-agente.
- Recuperação após crash real (processo filho, checkpoint SQLite e PostgreSQL) retoma sem repetir a triagem.
- Efeitos duplicados: o multi-agente executa 1 efeito; a baseline sem idempotência executa 2.
- Latência: a baseline é muito mais rápida nos pedidos simples (ver `docs/learn/09`).

## Limites deste estudo

Sem LLM real, sem chaves, sem medição de qualidade de decisão. A baseline foi escrita com as mesmas regras dos cenários. Estes números mostram coerência e durabilidade, não superioridade do multi-agente em pedidos reais.
