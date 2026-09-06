# FK composta por inquilino em tabela multi-tenant (conserto pós-adversário do L4-01-a-pacote-de-ativos)

Status: aceita. Turno 3, 06/09/2026.

## Contexto

O adversário independente do item L4-01-a (`handoffs/T3/ataque-L4-portal-ADVERSARIO.md` §1, achado A1)
mostrou que uma FK simples (`xxx_id uuid REFERENCES outra_tabela(id)`) entre duas tabelas que têm
`tenant_id` não é filtrada pela RLS: o inquilino B, autenticado como `plat_app` no próprio contexto,
consegue inserir uma linha SUA cujo `xxx_id` aponta para o `id` de uma linha do inquilino A — a FK só
confere que o id existe em algum lugar da tabela, nunca que é do mesmo `tenant_id`. Isso também vira um
oráculo de existência (uuid alheio é aceito, uuid inventado dá `ForeignKeyViolation`).

## Decisão

Toda FK entre duas tabelas que tenham `tenant_id` passa a ser **composta**: `(tenant_id, id)` no lado
referenciado (exige `UNIQUE (tenant_id, id)` lá — trivial, pois `id` já é único sozinho) e `(tenant_id,
xxx_id) REFERENCES alvo (tenant_id, id)` no lado que referencia. Com `MATCH SIMPLE` (o padrão do Postgres),
uma coluna nula na FK composta não é conferida, então uma referência opcional (`terminal_id`, `tipo_id`)
mantém a mesma nulidade de antes.

Aplicado nas 10 tabelas `plat.rede_*` em `db/migracoes/20260906T1815_rede_fk_por_inquilino.sql`. A trava
fica em `tests/api/test_fk_composta_por_inquilino.py`: varre `pg_constraint` do schema inteiro (não só a
rede) e reprova qualquer FK simples nova entre tabelas com `tenant_id`. A varredura achou 55 ocorrências do
mesmo padrão em tabelas de outros itens (a maioria apontando para `plat.usuario`/`plat.item`/`plat.pasta`
via `dono_id`/`criado_por`); documentadas em `PERMITIDAS` no próprio teste como fora de escopo deste item —
não corrigidas aqui.

## Alternativa considerada

Gatilho (`BEFORE INSERT/UPDATE`) conferindo `tenant_id` do alvo contra o da linha. Descartada por padrão:
mais um objeto por tabela para manter, sem ganho sobre a FK composta quando o alvo já tem `tenant_id` na
mesma linha (é o caso de toda tabela desta rede). Fica registrada como opção para quando o alvo não tiver
uma coluna id "verticalmente" alcançável na mesma tabela do `tenant_id` (não é o caso aqui).

## Consequência

Toda migração nova que crie uma FK entre tabelas com `tenant_id` cai na trava se não for composta — o erro
aparece em `make check`, não em produção. `erro_do_banco` (`app/auth/comum.py`) já mapeia
`ForeignKeyViolation` para 409; nenhuma mudança de contrato de erro foi necessária.
