# Spec Delta

## Purpose

Provar com cenários reproduzíveis que o sistema se comporta como especificado e medir honestamente quando a abordagem multi-agente compensa face a um workflow determinístico.

## ADDED Requirements

### Requirement: Cenários de demonstração automatizados
O projecto SHALL incluir cenários executáveis para: pedido simples resolvido, pedido dividido em 3 subtarefas, pedido que exige aprovação, rejeição pelo revisor, recuperação após reinício, tool injection bloqueada e retry sem efeito duplicado.

#### Scenario: Suite de cenários em modo fake
- **WHEN** se executa a suite de cenários com o provider falso
- **THEN** cada cenário reporta passou/falhou e a suite termina com código diferente de zero se algum falhar

### Requirement: Métricas de execução
O runner SHALL medir, por cenário e no agregado: taxa de conclusão, chamadas de LLM e de ferramentas por tarefa, tempo até aprovação, latência, custo estimado e efeitos duplicados evitados.

#### Scenario: Relatório gerado
- **WHEN** a suite termina
- **THEN** é gerado um JSON com as métricas, a data, o commit e o modo do provider

### Requirement: Baseline determinística
O projecto SHALL incluir um workflow determinístico (regras fixas sem supervisor) para os mesmos cenários e MUST reportar lado a lado a taxa de sucesso, a latência e o custo de ambos.

#### Scenario: Comparação honesta
- **WHEN** a comparação é executada
- **THEN** o relatório mostra os cenários em que a baseline é igual ou melhor, sem omitir nenhum

### Requirement: Honestidade dos números
Os relatórios MUST conter apenas valores medidos e identificar o provider usado. Valores não medidos MUST aparecer como `TODO: medir`.

#### Scenario: Sem Postgres real
- **WHEN** os testes de recuperação correm sem Postgres real
- **THEN** o relatório marca a recuperação após crash como `não verificado com Postgres real`
