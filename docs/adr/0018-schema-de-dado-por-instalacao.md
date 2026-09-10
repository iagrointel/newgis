# ADR 0018 — o schema de dado de camada carrega a instalação

Data: 07/09/2026. Estado: aceito. Origem: achado F8 do adversário do reescritor de schema
(`laco/handoffs/T4/ADVERSARIO-reescritor-schema.md`).

## Contexto

A plataforma põe o dado de cada inquilino num schema próprio, `d_<slug>`, derivado só do APELIDO do
inquilino (`app/ingestao/carregar.py`, `db/migracoes/029_ingestao_vetor.sql`). Homologação e as trilhas
de teste falam com um schema de controle diferente (`plat_homolog`, `plat_t<trilha>`) por REESCRITA DE
TEXTO da consulta (`app/schema_ambiente.py`), que troca a palavra `plat`. O nome `d_demo` não contém a
palavra `plat`: nenhuma reescrita o alcança. Resultado medido em 07/09/2026 no `iagro_sat`: o schema
`d_demo` tinha 79 tabelas, 14 do produto e 65 de sete trilhas de teste diferentes.

O passo 0 do job de carga é `DROP TABLE IF EXISTS "d_<slug>"."<tabela>" CASCADE`. Duas instalações que
gerem o mesmo nome de tabela apagam a camada uma da outra. A carga chama `ogr2ogr`, um subprocesso que
fala com o banco por `PG:` e não passa por psycopg2 — nenhuma camada de reescrita em Python o alcança.

## Decisão

O prefixo do schema de dado passa a incluir a instalação, por uma função no próprio schema de controle:

    plat.camada_schema_prefixo() -> 'd_'                  em produção
                                 -> 'd_plat_homolog_'     em homologação
                                 -> 'd_plat_t<trilha>_'   numa trilha

A função é escrita como `CASE WHEN 'plat' = 'p' || 'lat' THEN 'd_' ELSE 'd_' || 'plat' || '_' END`: o
reescritor troca a PALAVRA `plat`, e não a concatenação `'p' || 'lat'`, então em produção os dois lados
são iguais e o prefixo continua `d_`. **Produção não muda de lugar e nada é renomeado.**

`camada_schema_garantir`, `camada_preparar`, `tenant_criar` e `app/ingestao/carregar.py` passam a usar o
prefixo. A conferência de dono do schema em `camada_preparar` também (`prefixo || slug = p_schema`).

## Consequências

- `laco/trilha_ambiente.sh` deixa de dar `USAGE, CREATE` e `SELECT/INSERT/UPDATE/DELETE` nos schemas de
  dado de produção quando o worktree tem o conserto; a trilha só recebe privilégio no schema dela. O
  privilégio antigo continua para worktree sem o conserto, senão os ramos em andamento quebram.
- As 68 tabelas que trilhas já deixaram em `d_demo`/`d_demo2` NÃO são apagadas por esta mudança: a
  lista está no laudo `laco/handoffs/T4/F8-isolamento-d-slug.md` e a limpeza é decisão do dono.
- Teste que fixava `'d_demo'` no texto passa a perguntar o prefixo à instalação — dois já foram
  corrigidos (`test_ingestao.py`, `test_ingestao_100k.py`), porque mediam produção de dentro da trilha.
- Fica de fora desta decisão a outra classe do mesmo achado: nome GLOBAL ao cluster que não é schema
  (chave de advisory lock, F5 do laudo do adversário).
