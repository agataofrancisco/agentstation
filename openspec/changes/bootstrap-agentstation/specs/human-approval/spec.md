# Spec Delta

## Purpose

Garantir que nenhuma acção com efeito externo ou irreversível acontece sem a decisão explícita de um humano autorizado, de forma auditável e idempotente.

## ADDED Requirements

### Requirement: Interrupção obrigatória para acções mutáveis
Qualquer ferramenta marcada como `mutating` MUST levar o grafo a pausar e a criar um pedido de aprovação com `approval_id`, a acção proposta, os parâmetros, a justificação e as evidências. A acção NÃO SHALL ser executada antes de ser aprovada.

#### Scenario: Pedido de reset de MFA
- **WHEN** o fluxo conclui que o utilizador `joao@nimbo` precisa de reset de MFA
- **THEN** a tarefa fica `awaiting_approval` e nenhuma alteração é feita até haver decisão

### Requirement: Interrupção por risco ou falta de evidência
O sistema SHALL também pedir aprovação quando o verificador indicar pouca evidência, risco alto ou conflito com a política, mesmo que a acção não seja mutável.

#### Scenario: Procedimento contraditório
- **WHEN** dois procedimentos recuperados dão instruções opostas
- **THEN** a tarefa pausa com o motivo `conflicting_evidence` para revisão humana

### Requirement: Decisões do revisor
Um utilizador com papel `reviewer` ou `admin` do mesmo tenant SHALL poder aprovar, rejeitar ou editar os parâmetros. Requesters NÃO SHALL resolver aprovações, incluindo as suas.

#### Scenario: Rejeição
- **WHEN** um reviewer rejeita a acção com um comentário
- **THEN** a acção não é executada, o grafo retoma pelo ramo de rejeição e a tarefa termina com `rejected` e o comentário

#### Scenario: Edição antes de aprovar
- **WHEN** um reviewer altera a duração de uma suspensão de 30 para 7 dias e aprova
- **THEN** a acção é executada com 7 dias e a auditoria regista os valores original e editado

#### Scenario: Requester tenta aprovar
- **WHEN** o requester chama `POST /approvals/{id}/resolve`
- **THEN** o sistema devolve `403`

### Requirement: Efeitos exactamente uma vez
Uma acção aprovada MUST ser executada no máximo uma vez, mesmo que o nó seja reexecutado na retoma ou que a resolução seja enviada duas vezes. Cada efeito SHALL usar uma chave de idempotência derivada da tarefa e da aprovação.

#### Scenario: Resolução duplicada
- **WHEN** a mesma aprovação é enviada duas vezes
- **THEN** a segunda chamada devolve o resultado já registado e a acção não é repetida

#### Scenario: Reexecução do nó após retoma
- **WHEN** o nó que executa a acção é corrido de novo após um crash
- **THEN** a chave de idempotência impede a segunda execução e o evento `duplicate_effect_prevented` é registado

### Requirement: Auditoria
Cada pedido e decisão de aprovação MUST ficar registado de forma imutável: quem, quando, decisão, parâmetros e resultado da execução.

#### Scenario: Consulta de auditoria
- **WHEN** um admin consulta uma aprovação resolvida
- **THEN** vê o pedido original, o revisor, a decisão, o timestamp e o resultado
