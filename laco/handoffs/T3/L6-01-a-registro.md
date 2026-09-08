# Handoff — item L6-01-a-registro (arquiteto + backend, passagem única)

**Objetivo.** Registro de camadas do acervo: `plat.acervo_camada`, uma linha por TABELA canônica
com geometria no servidor principal (fonte_id, schema.tabela, SRID, tipo de geometria, lista branca
de colunas expostas, COUNT(*) exato com data, sha256 quando existir, estado exposta/bloqueada/
pendente_de_licenca), sincronizada por script idempotente rodando em ≤ 5 min.

## Este item é DIFERENTE de L6-01-a-procedencia-acervo (ENTREGUE) — não duplica

Conferido ANTES de escrever qualquer código: `grep -rn acervo_camada` na árvore inteira não achava
nada (021_acervo_ficha.sql, `app/acervo/*`, `tests/api/test_acervo.py` só tratam de
`plat.acervo_ficha`, view de METADADO DE FONTE — 376 linhas, sem geometria, sem `schema`/`tabela`/
`SRID`/coluna nenhuma de banco). A hipótese de `L6-01-a-registro` em `estado.json` pede exatamente o
oposto: registro por CAMADA (tabela com geometria), que não existe em lugar nenhum do repositório.
Os dois convivem: `acervo_camada.fonte_id` referencia a mesma `acervo.fonte` que a ficha descreve;
a ficha (021) NÃO é reaproveitada por esta migração (schemas diferentes de informação), mas os dois
usam a MESMA regra de licença (D17: `licenca IS NOT NULL AND btrim(licenca) <> ''`).
**Não coberto pelo já entregue — construído do zero, sem duplicar nada.**

## O que fiz

- `db/migracoes/027_acervo_camada.sql` (aplicada via `sudo bash db/migrar.sh`, registrada em
  `plat.versao_migracao`): `plat.acervo_camada` (sem `tenant_id`/RLS — registro GLOBAL da casa,
  mesmo padrão de `plat.acervo_ficha`) + `plat.acervo_camada_execucao` (histórico de rodadas);
  `GRANT SELECT` a `plat_app`, `REVOKE INSERT/UPDATE/DELETE` (só `scripts/acervo_sync.py`, como
  `postgres`, escreve).
- `scripts/acervo_sync.py`: sincronizador standalone (psycopg2 do dpkg, sem venv — roda como
  `postgres`, `sudo -u postgres python3 scripts/acervo_sync.py`). Candidatas = `acervo.objeto`
  (`tipo='fonte'`, `canonico`, servidor `vultr`, banco `iagro_sat`) × `geometry_columns`; `COUNT(*)`
  exato sob `SET LOCAL statement_timeout = 25000` (mesmo padrão do `contagem2.py` da casa, citado na
  hipótese do item); tabela fantasma = regra DINÂMICA (`linhas_exatas = 0 AND linhas_estimadas >
  0`), nunca lista de nomes; lista branca de colunas por NOME exato contra um deny-list pequeno de
  identificador de pessoa (rede mínima e PROVISÓRIA — o reforço por CONTEÚDO é o item L6-01-f,
  ainda não construído, e não é dependência declarada deste item); estado por licença (D17, mesmo
  critério de `plat.acervo_ficha`). Prazo duro de 270 s dentro do script; candidatas que sobram
  entram `bloqueada`/`nao_processada_no_prazo`. Ordem por `sincronizado_em` mais antigo primeiro
  (nunca sincronizada primeiro), para que rodadas sucessivas cubram tabelas diferentes.
- `docs/adr/0012-registro-do-acervo-e-conexao-externa.md` (Parte 1): decisões, medições, e o achado
  de que `--limite` de depuração apagava o registro completo (poda corrigida para comparar contra o
  universo INTEIRO de candidatas, não contra o que a rodada limitada processou).
- `docs/PARIDADE.md`, `MANUAL.md` §18.1, `ARQUITETURA.md` §15, `CHANGELOG.md`: seções novas.
- `tests/api/test_acervo_camada.py`: 6 testes rápidos + 1 `lento` (rodada completa).

## Evidência (comando + saída literal)

Migração numerada na hora: primeiro escrita como `028_acervo_camada.sql`... não — foi `027` desde o
início (livre no momento); o colisor de número foi o segundo item desta mesma passagem
(`030_conexao.sql`, ver handoff do outro item). `ls db/migracoes | tail -5`:
```
026_jobs_manutencao_analyze.sql
027_acervo_camada.sql
028_documento_grafo.sql
029_ingestao_vetor.sql
030_conexao.sql
```
(028/029 são de uma trilha concorrente rodando no mesmo repositório — nada delas foi tocado.)

Candidatas medidas 06/09/2026 (`geometry_columns` × `acervo.objeto`, servidor `vultr`, banco
`iagro_sat`): **462 candidatas totais, 270 em `public`** (perto do "462/269" da hipótese do item —
a pequena diferença é o acervo mudando entre varreduras; nunca digitado, só medido de novo).

Duas rodadas completas (`sudo -u postgres python3 scripts/acervo_sync.py`), máquina disputada por
outro job pesado da casa no mesmo intervalo (`REFRESH MATERIALIZED VIEW` de 3 h e `COUNT(*)` de 18
min de outra frente, confirmado em `pg_stat_activity`):
```
[acervo_sync] candidatas=462 expostas=81 bloqueadas=292 pendentes_de_licenca=87 fantasmas=0 nao_concluidas=2 removidas=0 duracao_s=274.9 estourou_prazo=True
real    4m34.950s
[acervo_sync] candidatas=462 expostas=172 bloqueadas=192 pendentes_de_licenca=93 fantasmas=0 nao_concluidas=5 removidas=0 duracao_s=286.0 estourou_prazo=True
real    4m46.099s
```
81→172 expostas da 1ª para a 2ª rodada: prova de que a ordem "há mais tempo sem sincronizar"
converge (rodadas sucessivas processam tabelas diferentes, não sempre as mesmas primeiras).

Depois do fix de contagem (`bloqueadas` agora soma TODOS os motivos de bloqueio, não só o de
prazo): `candidatas=462 expostas=149 bloqueadas=292 pendentes_de_licenca=21 fantasmas=0
nao_concluidas=3` → 149+292+21=462 exatamente.

Suíte (sob `flock laco/.pytest.lock`):
```
tests/api/test_acervo_camada.py ......                                   [100%]
6 passed, 1 deselected, 1 warning in 68.15s
tests/api/test_acervo_camada.py::test_execucao_completa_registra_estatisticas .  [100%]
1 passed, 1 warning in 297.93s (0:04:57)   # rodada COMPLETA das 462 candidatas, sob o portão de 5 min
```

## Riscos

Lista branca de coluna é NOME apenas (não CONTEÚDO) — depende do item L6-01-f para ficar completa;
até lá é rede mínima, documentada como tal em 3 lugares (script, migração, ADR). Máquina com outro
job pesado concorrente faz uma rodada isolada cobrir só ~35-40% das candidatas antes do prazo —
esperado e honesto (nunca finge cobertura), mas o cron semanal (B5/L6-01-h, não construído) precisa
rodar com frequência suficiente para convergir.

## Pendências

L6-01-b (view só-leitura + RLS por assinatura sobre a tabela original), L6-01-c (tela), L6-01-f
(LGPD por conteúdo), L6-01-g (licença curada em vocabulário fechado), L6-01-h (agendamento
automático via L0-05 — hoje o script roda manual/cron externo).

## Para o próximo papel

L6-01-b lê `plat.acervo_camada.estado = 'exposta'` para decidir quais tabelas ganham view
`SECURITY INVOKER` com RLS por assinatura; `colunas_expostas` já vem pronta como lista branca
inicial (reforçar com L6-01-f antes de considerar suficiente para LGPD).

## Resumo (8 linhas)

`plat.acervo_camada` registra 462 tabelas canônicas com geometria (270 em `public`), sincronizadas
por `scripts/acervo_sync.py` (COUNT(*) exato, timeout 25s, nunca reltuples). Tabela fantasma é regra
dinâmica (estimativa>0/exata=0), cobre as 2 conhecidas sem citar nomes. Estado depende da licença
D17 (mesma regra da ficha 021). Duas rodadas completas medidas (274,9s e 286,0s, sob o portão de 5
min), com convergência provada entre rodadas (81→172 expostas) apesar de outro job pesado da casa
disputando a máquina. Achado e corrigido: `--limite` de depuração apagava o registro inteiro antes
do fix de poda. 7 testes (`tests/api/test_acervo_camada.py`), 1 deles cobrindo a rodada completa.
Migração 027; ADR 0012.

**Commit:** `9df2cff` (enterprise repo).
