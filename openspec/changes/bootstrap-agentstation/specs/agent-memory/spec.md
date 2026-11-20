# Spec Delta

## Purpose

Permitir que os agentes recordem factos úteis entre tarefas de forma controlada, visível e apagável, sem guardar dados sensíveis nem instruções não confiáveis.

## ADDED Requirements

### Requirement: Memória longa opt-in e com escopo
A memória semântica de longo prazo SHALL estar desligada por omissão e ser activada por utilizador. Cada memória MUST ter `tenant_id`, `user_id`, origem (tarefa e evento), data de criação e expiração.

#### Scenario: Memória desligada
- **WHEN** um utilizador não activou a memória
- **THEN** nenhuma memória longa é escrita nem lida nas suas tarefas

#### Scenario: Isolamento
- **WHEN** um utilizador de `atlas` executa uma tarefa
- **THEN** nenhuma memória de `nimbo` é recuperada

### Requirement: Filtro de escrita
O sistema NÃO SHALL gravar em memória segredos, credenciais, dados pessoais sensíveis nem texto proveniente de conteúdo não confiável sem confirmação.

#### Scenario: Tentativa de memorizar uma password
- **WHEN** uma tarefa contém "a password temporária é Xy7!..."
- **THEN** essa informação não é gravada e o evento `memory_write_blocked` é registado

### Requirement: Transparência e eliminação
O sistema SHALL mostrar em cada tarefa quais as memórias recordadas e o motivo. O utilizador MUST poder listar e eliminar as suas memórias.

#### Scenario: Eliminar memória
- **WHEN** o utilizador chama `DELETE /memory/{id}`
- **THEN** a memória deixa de ser recuperada em tarefas futuras

#### Scenario: Memória expirada
- **WHEN** a data de expiração de uma memória passou
- **THEN** essa memória não é recuperada
