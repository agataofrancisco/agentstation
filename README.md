# AgentStation

Orquestração multi-agente com estado durável e aprovação humana obrigatória para acções mutáveis.
Domínio fictício: helpdesk da **Nimbo Software** (tenant `nimbo`) e **Atlas Retalho** (`atlas`, para isolamento). Todos os dados são sintéticos.

## Estado actual

- Backend (FastAPI + LangGraph + SQLAlchemy/Alembic + Celery): implementado e testado.
- Checkpointer PostgreSQL e recuperação após crash: testados com PostgreSQL real (`pgserver`, sem Docker),
  incluindo um worker Celery real interrompido e outro que retoma sem repetir a triagem.
- Frontend React: implementado e com build validado. O diagrama do grafo e a linha
  temporal foram verificados no browser (cenário de 3 subtarefas). Porta de desenvolvimento: `13100`.
- Docker/compose: `docker compose config` válido; `docker compose up` **não testado** (daemon Docker indisponível).
- Revisão de segurança: auto-revisão e revisão independente em `docs/security-review-independent.md`.
  Permanecem os limites documentados nessa revisão.

## Executar localmente (sem Docker, sem chaves de API)

Requisitos: Python 3.12. Correr a partir da raiz do projecto.

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows (Git Bash: source .venv/Scripts/activate)
pip install -e ".[dev]"
export DATABASE_URL=sqlite:///data/runtime/demo.db
export CHECKPOINT_URL=sqlite:///data/runtime/demo_cp.db
export CELERY_EAGER=true          # sem worker separado (demo); LLM_PROVIDER=auto usa o provider falso sem chave
alembic -x url=$DATABASE_URL upgrade head
python -m backend.app.seed
python -m uvicorn backend.app.api.app:create_app --factory --port 18100
```

Exemplo (login por persona, sem palavra-passe, só com `DEMO_MODE`):

```bash
curl -s -X POST http://127.0.0.1:18100/auth/login -H 'Content-Type: application/json' -d '{"email":"ines@nimbo"}'
```

Personas: `ines@nimbo` (requester), `joao@nimbo` (requester), `rui@nimbo` (reviewer), `ada@nimbo` (admin), `marta@atlas` (requester), `pedro@atlas` (reviewer).

Testes e qualidade:

```bash
ruff check . && ruff format --check .
pytest -m "not postgres"          # rápido
pytest -m postgres                # PostgreSQL real via pgserver
python -m eval.runner --reps 3    # cenários + baseline -> eval/results/latest.json
```

## Documentação

- `docs/architecture.md` — componentes e fluxos.
- `docs/decisions.md` — decisões e decisões novas tomadas na implementação.
- `docs/case-study.md` — resumo do caso e resultados medidos.
- `docs/learn/` — material de aprendizagem (pt-PT), incluindo `10-perguntas-de-entrevista.md`.
- `openspec/changes/bootstrap-agentstation/` — especificação e plano.
