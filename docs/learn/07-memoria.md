# 07 — Memória de longo prazo

## O problema

Um agente que aprende entre tarefas é útil: se o mesmo problema volta, pode recordar o procedimento que funcionou. Mas memória é também o sítio onde dados sensíveis se acumulam sem ninguém reparar, e onde uma instrução maliciosa de um ticket se pode tornar "facto" para tarefas futuras. Por isso a memória é **opt-in**, **com escopo** (tenant e utilizador), **com validade**, **filtrada à escrita** e **apagável**.

## O que entra e o que sai

Entra o texto candidato a memória (pedido + resumo da tarefa: ids de ticket e de procedimentos, sem corpo de tickets). Sai uma memória com `tenant_id`, `user_id`, `source_task`, `created_at` e `expires_at`, ou um evento `memory_write_blocked` com o motivo.

Saída real do filtro de escrita (`backend/app/memory/filter.py`):

```text
'a password temporaria e Xy7!abc' untrusted= False -> (False, 'secret')
'contacto 912345678' untrusted= False -> (False, 'personal_data')
'resumo sem dados' untrusted= True -> (False, 'untrusted_origin')
'classifica o ticket T-101 | Ticket T-101; procedimentos: PR-01' untrusted= False -> (True, None)
```

## Como funciona por dentro

- **Opt-in**: `users.memory_enabled` (`backend/app/store/models.py`). Por omissão é `False`. O seed activa-o só para `ines@nimbo` e `marta@atlas`, para demonstração. Não há ainda um endpoint para o utilizador activar a memória; isto fica como limitação (ver abaixo).
- **Recordar**: na primeira visita do supervisor (`_recall`, `backend/app/graph/control_nodes.py`), se o utilizador tiver memória activa, procura-se por similaridade e regista-se `memory_recalled` com os ids e textos recordados. A linha temporal mostra por tarefa o que foi recordado.
- **Escrever**: no `finalize`, só para tarefas `completed` e utilizadores com memória activa (`_remember`). O candidato passa por `write_decision`. Se for bloqueado, regista-se `memory_write_blocked` com o motivo.
- **Filtro** (`backend/app/memory/filter.py`): bloqueia origem não confiável (tarefa com `suspected_injection`), segredos (palavra-passe, token, chave API), e dados pessoais (email, IBAN, NIF de 9 dígitos, telemóvel).
- **Armazenamento** (`backend/app/memory/store.py`): ChromaDB com uma colecção por tenant (`mem_{tenant}`). A consulta filtra por `user_id` e por `expires_at > agora` no próprio Chroma, por isso memórias expiradas nunca são devolvidas.
- **Eliminação**: `DELETE /memory/{id}` só funciona para o dono; outro utilizador do mesmo tenant recebe `404`, como se a memória não existisse.
- **Idempotência**: o id da memória é `mem-{task_id}`, por isso reexecutar o `finalize` não duplica.

## Porquê esta escolha

- **Filtrar à escrita e não à leitura**: uma memória errada, uma vez gravada, contamina todas as tarefas futuras. Bloquear na entrada é mais barato do que limpar depois.
- **Tenant como colecção**: o isolamento não depende de um filtro na consulta; uma consulta de outro tenant nem toca nas memórias.
- **Expiração no armazenamento**: a regra de validade é aplicada pela própria consulta, não por um job de limpeza que pode atrasar.

## Alternativas

- **Memória sem opt-in**: rejeitada pela spec e por privacidade.
- **Filtro com LLM** (classificar se o texto é sensível): mais flexível, mas outro modelo a confiar e custo por escrita. Usamos regras explícitas, que são testáveis e auditáveis.
- **Embeddings de um modelo real**: melhor qualidade de recuperação. Usamos bigramas por hashing para funcionar sem rede. Isto é uma **aproximação de demonstração**; a qualidade de recuperação não foi medida.

## Limitações honestas

- O filtro é por padrões. Um dado pessoal num formato não previsto passa. A regra de defesa principal é não gravar conteúdo de tickets (só ids e categorias do resumo), não o filtro.
- Os embeddings por hashing não têm qualidade semântica comprovada; não há métrica de recuperação. **TODO: medir** se for usada em produção.
- Não há endpoint para o utilizador activar ou desactivar a memória (só o seed, para demonstração).
- O filtro usa a lista de termos em português e inglês; sinónimos fora dela passam.

## Como falha (e onde está testado)

| Risco | Teste |
|---|---|
| Memória escrita para quem não activou | `tests/test_memory.py::test_memory_disabled_by_default_writes_nothing` |
| Password no pedido não é gravada e fica registada | `test_secret_in_request_is_not_stored_and_is_recorded` |
| Dados pessoais e origem não confiável bloqueados | `test_write_filter_blocks_personal_data_and_untrusted_origin` |
| Isolamento entre tenants e utilizadores | `test_store_isolates_tenants_and_users_and_expires` |
| Memória expirada não é recuperada | mesmo teste (consulta a 2 dias de distância) |
| Eliminação só pelo dono | `test_user_can_delete_own_memory_and_others_get_404` |
| Recordação visível na linha temporal | `test_opt_in_user_gets_memory_and_recall_is_recorded` |

## Perguntas de entrevista

1. **Porque filtrar à escrita?** Porque uma memória envenenada persiste e afecta tarefas futuras; limpar depois não garante que ninguém a leu.
2. **Como se garante isolamento entre tenants?** Colecções separadas por tenant; a consulta nunca cruza colecções.
3. **Porque é que a expiração não depende de um job?** Porque a consulta já filtra por `expires_at`; o job só libertaria espaço.
4. **O que falta para uma memória de produção?** Consentimento explícito e revogação em massa, medição da qualidade de recuperação e um filtro de dados pessoais revisto por quem tem responsabilidade legal.
