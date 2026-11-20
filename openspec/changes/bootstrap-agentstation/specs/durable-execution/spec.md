# Spec Delta

## Purpose

Garantir que uma tarefa de agentes guarda o seu estado em cada passo e pode retomar depois de uma falha, sem perder trabalho nem repetir efeitos.

## ADDED Requirements

### Requirement: Checkpoint por passo
O estado do grafo MUST ser persistido numa base de dados durável depois de cada passo, associado a um `thread_id` igual ao id da tarefa. A fila de jobs NÃO SHALL ser usada como armazenamento do estado do grafo.

#### Scenario: Inspecção do estado
- **WHEN** uma tarefa está a meio da execução
- **THEN** o último checkpoint está guardado e indica o nó actual e o estado acumulado

### Requirement: Retoma após falha
Se a API ou o worker forem reiniciados a meio de uma tarefa, o sistema SHALL retomar a partir do último checkpoint, sem repetir passos já concluídos com efeitos.

#### Scenario: Worker morre durante a tarefa
- **WHEN** o processo do worker é terminado depois do passo `triage` e antes de `knowledge_retrieval`
- **THEN** após o reinício a tarefa continua em `knowledge_retrieval` e o resultado da triagem não é recalculado

#### Scenario: API reiniciada com aprovação pendente
- **WHEN** a API reinicia enquanto uma tarefa espera aprovação
- **THEN** a aprovação continua listada em `GET /approvals` e pode ser resolvida normalmente

### Requirement: Histórico de eventos
Cada tarefa SHALL ter um log de eventos ordenado (início de nó, chamada de ferramenta, resultado, pedido de aprovação, decisão, erro, conclusão), com timestamps, consultável depois de a tarefa terminar.

#### Scenario: Linha temporal
- **WHEN** um reviewer abre uma tarefa concluída
- **THEN** vê todos os eventos por ordem, com o agente, a ferramenta e a duração de cada passo
