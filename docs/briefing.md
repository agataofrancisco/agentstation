# PROMPT 02 — AgentStation: sistema multi-agente com memória e human-in-the-loop

## Missão
Cria uma estação de trabalho de IA para gerir pedidos internos de uma empresa fictícia de transporte: triagem de tickets, consulta de políticas internas e elaboração de respostas/relatórios. Deve haver supervisor, agentes especializados, execução auditável, ferramentas reais de dados DEMO e aprovação humana para qualquer efeito externo. Nunca enviar mensagens, editar tickets ou executar operações irreversíveis sem aprovação explícita.

## Arquitectura
- Backend Python FastAPI, LangGraph com StateGraph explícito; PostgreSQL para dados da aplicação e checkpoints duráveis; ChromaDB para recuperar memórias semânticas opt-in; Redis + Celery para jobs de ingestão/análises demoradas. NÃO usar Redis/Celery para substituir o estado persistente da execução do grafo.
- LLM via provider abstraction compatível OpenRouter/OpenAI com modelos configuráveis e fake provider determinístico. Não depender de nome de modelo específico.
- Supervisor decompõe solicitações e delega a pelo menos 3 agentes com responsabilidades limitadas: `triage`, `knowledge_retrieval`, `reporting`; nó de verificação independente valida schemas, evidências e permissões. Grafo deve conter limites de iterações, ferramentas, tempo, tokens e custo.
- Ferramentas com schemas Pydantic: consultar base de tickets, consultar documentos permitidos, criar rascunho de resposta, propor actualização de estado; tool registry allowlisted, checagem de autorização no backend, idempotency keys.
- Memória de curto prazo como checkpoints por thread; memória longa semântica opcional separada por tenant/utilizador, com origem, expiração e remoção; não gravar automaticamente dados sensíveis ou instruções não confiáveis em memória. Apresentar o que foi recordado e permitir eliminar.
- Para qualquer `mutating_action`, e quando houver insuficiência de evidência, risco ou política, utilizar `interrupt()` e `Command(resume=...)`; persistir pedido de aprovação com `approval_id`, estado e auditoria. Atenção: o nó que retoma pode reexecutar; coloca efeitos externos depois da aprovação com idempotência.

## Experiência
Frontend React ou Streamlit com: (1) lista de tarefas e estados, (2) diagrama do grafo actual, (3) linha temporal de agentes/tools, (4) fila de aprovações com aceitar/rejeitar/editar, (5) painel memória e justificações, (6) resultados exportáveis. Autenticação simples com papéis `requester`, `reviewer`, `admin`.

## API mínima
`POST /tasks`, `GET /tasks/{id}`, `GET /tasks/{id}/events` via SSE/polling, `GET /approvals`, `POST /approvals/{id}/resolve`, `GET /memory`, `DELETE /memory/{id}`, health/metrics. Workers e API executam de forma coordenada em Docker Compose com migrações.

## Cenários e critérios
Demonstra: pedido simples resolvido; pedido dividido em 3 subtarefas; pedido que necessita aprovação; rejeição pelo revisor; recuperação após reiniciar API/worker; tentativa de tool injection bloqueada; retry que não executa duas vezes uma operação. Testes de crash/restart, isolamento por tenant, idempotência, autenticação e acesso a memória. Mede taxa de tarefas concluídas, tempo até aprovação, chamadas por tarefa, custo e reexecuções evitadas; números só após correr os testes.

## Evidências
README com arquitectura do supervisor, estados do grafo, painel com execução de exemplo e uma análise concreta sobre quando o multi-agente é MELHOR ou PIOR que um workflow determinístico simples. Justifica trade-offs de latência/custo. Baseia interrupt/checkpointer nas docs actuais do LangGraph.

## Regras de execução (obrigatórias)
És um agente sénior de software engineering e AI engineering. A tua missão é IMPLEMENTAR código funcional neste repositório, não apenas escrever um plano ou pseudocódigo. Primeiro inspecciona o repositório; depois propõe em `IMPLEMENTATION_PLAN.md` um plano curto e segue-o por fases até teres uma versão executável. Não pares após criar ficheiros vazios. Usa documentação oficial actual das bibliotecas e fixa versões compatíveis; não inventes APIs nem dependências. Caso não tenhas acesso a rede/credenciais, implementa adaptadores, mocks determinísticos e testes locais, mas distingue explicitamente o que foi testado de verdade do que foi apenas preparado.

Normas comuns: Python 3.11+ (salvo indicação explícita), tipagem, Pydantic v2, configuração por `.env.example`, FastAPI com OpenAPI, Ruff, pytest, logging estruturado sem secrets/PII, Dockerfile, `docker-compose.yml` quando fizer sentido, healthcheck e README claro (arranque, decisões de arquitectura, ameaças, limitações, custos, credenciais e deploy). Não coloques chaves no cliente ou no Git; valida entradas, implementa timeouts/retries limitados e autenticacao para operações administrativas. Inclui modo DEMO com dados sintéticos e sem pagamento; implementa testes unitários e testes de integração determinísticos em CI, mais uma suite de integração real opcional. Escreve `docs/architecture.md`, `docs/decisions.md`, `docs/case-study.md` com métricas REAIS ou campos `TODO: medir` (nunca inventes resultados). Entrega exactamente os comandos de execução e testes e lista limitações.

Para deployment, prepara backend persistente numa VM/serviço de containers e frontend estático quando possível; não assumes que Vercel Functions suporta Redis, workers long-running, volumes persistentes ou treino GPU. Se houver persistência, usa serviço gerido/volume externo e documenta credenciais, migrações e backups. Antes de concluir, executa testes, corrige falhas, regista o output e documenta o que não foi possível executar.
