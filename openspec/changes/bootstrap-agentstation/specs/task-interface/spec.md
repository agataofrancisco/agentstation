# Spec Delta

## Purpose

Expor a criação, o acompanhamento e a revisão de tarefas por API e por um painel web, com papéis e estados claros.

## ADDED Requirements

### Requirement: API de tarefas
O sistema SHALL suportar `POST /tasks` (devolve `task_id` e estado `queued`) e `GET /tasks/{id}` (estado, subtarefas, resultado e limites consumidos). Os estados MUST ser `queued`, `running`, `awaiting_approval`, `completed`, `rejected`, `failed`, `limit_exceeded` ou `needs_review`.

#### Scenario: Criar tarefa
- **WHEN** um requester envia um pedido válido
- **THEN** recebe `202` com `task_id` e a tarefa é executada de forma assíncrona

### Requirement: Stream de eventos
`GET /tasks/{id}/events` SHALL enviar os eventos em tempo real por SSE e MUST permitir retomar a partir do último evento recebido.

#### Scenario: Reconexão
- **WHEN** o cliente reconecta com `Last-Event-ID`
- **THEN** recebe apenas os eventos posteriores, sem duplicados

### Requirement: Autenticação e papéis
Todos os endpoints, excepto o health, MUST exigir autenticação. Requesters vêem apenas as suas tarefas; reviewers e admins vêem as tarefas do tenant; ninguém vê outro tenant.

#### Scenario: Requester consulta tarefa alheia
- **WHEN** um requester pede `GET /tasks/{id}` de outra pessoa
- **THEN** recebe `404`

### Requirement: Painel web
O painel SHALL mostrar a lista de tarefas e os estados, o diagrama do grafo com o nó actual, a linha temporal de agentes e ferramentas, a fila de aprovações com aceitar, rejeitar e editar, o painel de memória e a exportação do resultado.

#### Scenario: Revisor resolve no painel
- **WHEN** um reviewer abre a fila e aprova um pedido
- **THEN** a tarefa sai de `awaiting_approval` e a linha temporal mostra a decisão

### Requirement: Saúde e métricas
O sistema SHALL expor `GET /health` (API, base de dados, fila e worker) e `GET /metrics`, só para admin, com tarefas por estado, tempo até aprovação, chamadas por tarefa, custo estimado e efeitos duplicados evitados.

#### Scenario: Worker em baixo
- **WHEN** nenhum worker está activo
- **THEN** `/health` reporta `worker: "down"` com estado global `degraded`
