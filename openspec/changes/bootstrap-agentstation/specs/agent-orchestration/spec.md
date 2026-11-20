# Spec Delta

## Purpose

Coordenar vários agentes com responsabilidades limitadas sob um supervisor, de forma auditável e dentro de limites rígidos de recursos.

## ADDED Requirements

### Requirement: Supervisor e agentes especializados
O sistema SHALL ter um supervisor que decompõe cada pedido em subtarefas e as delega nos agentes `triage`, `knowledge_retrieval` e `reporting`. Cada agente MUST ter acesso apenas às ferramentas da sua responsabilidade.

#### Scenario: Pedido com três subtarefas
- **WHEN** um requester pede "classifica o ticket T-104, encontra o procedimento aplicável e prepara uma resposta"
- **THEN** o histórico da tarefa mostra delegações para `triage`, `knowledge_retrieval` e `reporting`, por esta ordem de dependência

#### Scenario: Agente tenta ferramenta fora do seu âmbito
- **WHEN** o agente `reporting` tenta chamar a ferramenta `propose_account_action`
- **THEN** a chamada é recusada, registada como `tool_not_allowed` e a tarefa continua sem a executar

### Requirement: Verificação independente
Antes de concluir uma tarefa ou de pedir aprovação, um nó verificador SHALL validar o schema da saída, a existência de evidências citadas e as permissões do requester. Uma saída que falha a verificação MUST voltar ao supervisor ou terminar como `needs_review`.

#### Scenario: Resposta sem evidência
- **WHEN** o agente `reporting` produz uma resposta que não cita nenhum procedimento recuperado
- **THEN** o verificador rejeita-a e a tarefa não é marcada como `completed`

### Requirement: Limites de execução
Cada tarefa MUST respeitar limites configuráveis de iterações do grafo, chamadas de ferramentas, tempo total, tokens e custo estimado. Ao atingir um limite, a tarefa SHALL terminar com o estado `limit_exceeded` e o motivo.

#### Scenario: Ciclo infinito entre agentes
- **WHEN** o supervisor e um agente se reenviam a mesma subtarefa repetidamente
- **THEN** a tarefa termina com `limit_exceeded: max_iterations` antes de ultrapassar o limite configurado

#### Scenario: Orçamento de custo
- **WHEN** o custo estimado acumulado atinge o tecto da tarefa
- **THEN** não são feitas mais chamadas ao LLM e a tarefa termina com `limit_exceeded: max_cost`

### Requirement: Provider de LLM abstraído
O sistema SHALL usar o LLM através de uma interface compatível com OpenAI, com modelo configurável, e MUST incluir um provider falso determinístico que permita executar todos os cenários sem rede.

#### Scenario: Execução offline
- **WHEN** `DEMO_MODE=true` sem chave de API
- **THEN** os cenários de demonstração completam-se com o provider falso e os eventos indicam `provider: fake`
