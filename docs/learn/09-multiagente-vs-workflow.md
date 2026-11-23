# 09 — Multi-agente vs workflow determinístico

## O problema

Um supervisor com três agentes e um verificador custa mais e demora mais do que uma cadeia fixa de regras. A pergunta honesta não é "qual é melhor?", mas "em que cenários compensa, e quanto custa?". Este documento responde com números do relatório `eval/results/latest.json`, gerado por `python -m eval.runner --reps 3`.

## O que entra e o que sai

Entram os 7 cenários de demonstração (`eval/runner.py`) e a baseline (`eval/baseline.py`). Saem, por cenário: taxa de sucesso, estado final, efeitos, chamadas ao LLM e às ferramentas (medianas), latência mediana, custo estimado e efeitos duplicados evitados.

Resumo medido (commit `fc48b12`, provider `fake`, 3 repetições por cenário):

| Cenário | Multi-agente: sucesso / latência (ms) / LLM | Baseline: sucesso / latência (ms) / LLM |
|---|---|---|
| S1 pedido simples | 1.0 / 2421 / 10 | 1.0 / 5.6 / 0 |
| S2 três subtarefas | 1.0 / 2991 / 10 | 1.0 / 2.4 / 0 |
| S3 aprovação (aprovado) | 1.0 / 5561 / 11 | 1.0 / 44 / 0 |
| S4 rejeição | 1.0 / 2044 / 11 | 1.0 / 2.9 / 0 |
| S5 recuperação após crash | 1.0 / 58507 / 10 | não aplicável (sem checkpoint) |
| S6 injeção bloqueada | 1.0 / 1286 / 11 | 1.0 / 1.6 / 0 |
| S7 sem efeito duplicado | 1.0 / n.d. / 11 | **0.0** (2 efeitos) / 46 / 0 |

Custo estimado do multi-agente: ~0.01 USD por tarefa, calculado como `chamadas × 0.001` (valor fixo do provider fake, **não é um custo real**). Baseline: 0.

## Como funciona por dentro

- **Multi-agente**: `backend/app/graph/*` com supervisor, agentes, verificador e aprovação. Cada tarefa faz 10 a 11 chamadas ao LLM (o supervisor chama-se a cada passo).
- **Baseline**: `eval/baseline.py`, pipeline fixo: regex do ticket, procedimento por regra, aprovação quando há reset de MFA, sem chave de idempotência. Nenhuma chamada ao LLM.
- **Critério de sucesso**: o estado final e o número de efeitos têm de coincidir com o esperado definido no próprio cenário (`SCENARIOS` em `eval/runner.py`).

## Porquê esta escolha de medição

- Mesmos cenários e mesmo esquema de base de dados para os dois lados.
- A recuperação após crash é real para o multi-agente (processo filho termina com código `137`; o processo seguinte retoma). A baseline não tem estado a retomar, por isso não se aplica.

## Conclusões (cada uma ancorada no relatório)

1. **Latência**: a baseline é entre ~100× e ~1000× mais rápida nos pedidos simples (S1: 5.6 ms contra 2421 ms; S2: 2.4 ms contra 2991 ms). A diferença vem sobretudo das chamadas ao LLM; com um provider real, a latência do LLM dominaria e a diferença ficaria por medir.
2. **Custo**: a baseline não gasta chamadas ao LLM; o multi-agente gasta 10 a 11 por tarefa. Isto é uma estimativa com preço fixo, não uma medição de faturação.
3. **Efeitos duplicados**: só o multi-agente passa S7 (1 efeito). A baseline executa a acção duas vezes. Esta é a vantagem que justifica a idempotência do grupo 5, não a inteligência do agente.
4. **Recuperação**: só o multi-agente recupera (S5). Medido com processo filho real; o tempo de 58 s inclui o arranque de dois processos Python e inicialização de dependências, e não deve ser lido como latência de tarefa.
5. **Onde a baseline ganha**: em tudo o que é regra fixa (S1, S2, S4, S6). Nestes cenários o multi-agente chega ao mesmo resultado com mais custo. Os pedidos compostos ou ambíguos (texto livre sem ticket claro, procedimentos em conflito fora do caso MFA) **não estão cobertos por estes cenários**; a hipótese de que a baseline perderia nesses casos continua **não testada** (TODO: medir com cenários ambíguos).

## Limitações honestas (leia antes de citar os números)

- **A baseline não é independente.** Foi escrita com as mesmas regras que os cenários exigem, por isso a taxa de sucesso 1.0 em S1, S2, S4 e S6 mostra apenas que a regra funciona nos casos que a regra conhece. Não mostra superioridade ou inferioridade num conjunto de pedidos real.
- **Provider fake**: o LLM é determinista e escrito por nós. Qualquer comparação de qualidade de decisão do LLM é inválida. Não há medição de qualidade real.
- **n = 3 repetições**: medianas com amostra pequena. Os tempos variam por máquina.
- **S7 multi-agente sem latência**: o runner não mediu a latência deste caminho (a alteração ao cálculo não entrou); fica como `None` no relatório.
- **Custo** é `chamadas × 0.001` fixo. Não é custo real. Campos de latência e custo de LLM real: `TODO: medir` (ver `metadata` do relatório).

## Como falha (e onde está testado)

- A suite de cenários termina com código diferente de zero se o multi-agente falhar (`multi_agent_failed` em `eval/runner.py`).
- A baseline não usa a função de efeitos com idempotência; por isso S7 falha de propósito e está documentado.

## Perguntas de entrevista

1. **Quando é que um workflow determinístico ganha?** Quando as regras cobrem o problema. Nos nossos cenários, sim, em latência e custo.
2. **O que a vantagem do multi-agente realmente é aqui?** Recuperação e efeitos exactamente uma vez, que vêm da camada de durabilidade e não dos agentes.
3. **Porque é que a baseline não é uma prova?** Porque foi escrita com as mesmas regras que os testes exigem; é uma verificação de coerência, não uma comparação justa.
4. **O que medir a seguir?** Um conjunto de pedidos reais e ambíguos, com provider real e custo real, com a mesma regra de sucesso para os dois lados.
