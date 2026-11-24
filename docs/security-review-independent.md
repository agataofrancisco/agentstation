# Revisão de segurança independente

**Estado:** revisão estática concluída; achados documentados.
**Escopo:** `HEAD` `1fa707a` e árvore de trabalho em 2026-11-24, incluindo a implementação de workers ainda não commitada.
**Método:** leitura de autorização, resolução de aprovação, ferramentas, memória, JWT e revisão anterior. Não foram executados testes nem serviços externos.

## Achados

| ID | Severidade | Estado | Evidência e impacto |
|---|---|---|---|
| IR-1 | Alta | Corrigido no código; teste pendente | `resolve_approval` só exigia papel reviewer/admin e não comparava o revisor com `Approval.requester_id`. Como reviewers também podem criar tarefas, podiam aprovar a própria ação. Agora a resolução recusa autoaprovação. |
| IR-2 | Média | Mitigado no código; PostgreSQL pendente | Duas resoluções simultâneas podiam ler `pending` e gravar decisões contraditórias, cada uma com auditoria e retoma da tarefa. `resolve_approval` agora carrega a linha com `SELECT FOR UPDATE` e revalida o estado. O bloqueio efetivo precisa de confirmação no PostgreSQL; não foi executado nesta revisão. |
| IR-3 | Média | Aberto | `backend/app/tools/injection.py` deteta padrões, mas não é um limite de segurança semântico. A barreira efetiva é a allowlist, autorização no executor e aprovação humana para ferramentas mutáveis. Um prompt malicioso ainda pode induzir uma proposta errada para o revisor; a decisão humana continua a ser um controlo operacional. |
| IR-4 | Média | Aberto | `backend/app/memory/filter.py` bloqueia padrões conhecidos de segredos/PII. O próprio filtro e a auto-revisão reconhecem falsos negativos para formatos não previstos. Memória pode conter conteúdo sensível que o filtro não reconheça. |
| IR-5 | Média | Aberto | Tarefas, resultados e checkpoints não têm política de retenção; a memória tem TTL, mas os dados de execução permanecem. Definir retenção e eliminação também para tickets/resultados/checkpoints antes de uso com dados reais. |
| IR-6 | Baixa | Documentado | A auditoria é append-only pela aplicação, não por permissões/triggers na base de dados. Um acesso direto de escrita à base pode alterar eventos. |
| IR-7 | Baixa | Documentado | `DEMO_MODE` é falso por omissão e, fora de demo, exige segredo JWT configurado; isto falha fechado. Ainda assim, o JWT é HS256 sem rotação/issuer/audience, e o worker não tem autenticação de serviço separada. Deployment real requer gestão de identidade e de segredos. |

## Controlos observados

- Rotas e ferramentas filtram por `tenant_id`; recursos de outro tenant retornam `404` para ocultar existência.
- Ferramentas são allowlistadas, validam argumentos e não ecoam valores inválidos do modelo.
- A resolução de aprovação exige reviewer/admin, regista alterações e agora impede autoaprovação. Decisões repetidas depois de uma decisão concluída não alteram o estado.
- Dados das ferramentas são delimitados como entrada não confiável antes de serem enviados ao provider. Isto reduz a influência direta de instruções nos dados, mas não substitui aprovação/autorização.
- Segredos JWT de produção não têm valor padrão; o gancho de crash exige demo e flag explícitos.

## Parecer

A tarefa 10.5 foi revista e os achados estão documentados. IR-1 foi corrigido no código desta árvore; IR-2 usa bloqueio de linha, mas falta verificar concorrência em PostgreSQL. A revisão não aprova o sistema para produção enquanto retenção, falsos negativos da memória e os controlos de deployment permanecerem pendentes.
