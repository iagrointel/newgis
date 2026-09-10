# ADR 0018 — Métricas Prometheus da API/worker e exporters de infraestrutura

Item `L7-06-a-metricas-exporters`. ⚠️ Número provisório: em 07/09/2026 há VÁRIOS worktrees paralelos
reivindicando 0018 para outros itens (achado ao checar `ls docs/adr` nos worktrees antes de escrever
este arquivo) — renumerar no merge para o próximo livre em `master` naquele momento, nunca manter dois
0018 (mesma regra já em vigor para migrações, ADR 0014).

## Contexto

O laço exige métrica/painel/alerta (item-pai `L7-06-observabilidade`). Este item é só a base:
biblioteca de métrica na API e no worker, e os exporters de infraestrutura que faltavam (node-exporter
e Martin já tinham `/metrics` nativo antes deste item).

## Decisão

1. `prometheus_client` (apt `python3-prometheus-client`, a mesma biblioteca já citada como "padrão da
   casa" no próprio texto do item) num módulo único, `app/metricas.py`, com `CollectorRegistry` PRÓPRIO
   (não o `REGISTRY` global do pacote) — cada processo (API, worker) usa sua própria instância; nunca
   soma entre processos, o Prometheus soma pelos rótulos `job`/`instance` do scrape.
2. **Rótulo de rota é o PADRÃO da rota do roteador** (`request.scope["route"].path`), nunca o caminho
   redigido usado no log de acesso (`app.auth.redigir.rota_redigida`) — esse carrega o id do recurso e
   viraria cardinalidade sem limite como métrica.
3. **Rótulo de inquilino é sempre `tenant_id` (inteiro, `plat.tenant.id`), nunca o slug.** O schema de
   dado é `d_<slug>` (migração 029) e o slug pode ser o nome do cliente — a regra binária da casa
   ("nunca vazar nome de inquilino") vale para métrica com a mesma força que vale para documento.
4. **`application_name = 'plat:<tenant_id>'` por conexão com contexto** (`app/db.py::_preparar`) — é o
   único jeito de uma sessão EXTERNA (o `postgres_exporter`) enxergar o inquilino de outra sessão em
   `pg_stat_activity`; `current_setting('plat.tenant_id')` só lê a própria sessão. Sem contexto, a
   conexão volta para `application_name = 'plat'` — sem isso, uma conexão do POOL reaproveitada por um
   pedido sem contexto ficaria marcada com o inquilino anterior (achado rodando o teste de unidade).
5. **`postgres_exporter` com role dedicada `plat_metrica_pg`** (só `pg_monitor` + `SELECT` em
   `plat.tenant`) e os coletores `stat_user_tables`/`statio_user_tables` DESLIGADOS — medido: ligados,
   231.807 séries (o `iagro_sat` é compartilhado por dezenas de frentes, não é métrica nossa). Duas
   consultas próprias de baixíssima cardinalidade (`plat_tenant_schema_bytes`, `plat_tenant_conexoes`),
   as duas por `tenant_id`. `statement_timeout`/`lock_timeout` curtos na role: uma DDL concorrente de
   outra trilha travou 7 scrapes em `Lock/relation` até 4 min antes do ajuste.
6. **`nginx_exporter` com `stub_status` interno em `127.0.0.1:8096`**, arquivo de site PRÓPRIO
   (`deploy/nginx-metricas.conf`) — nunca dentro do vhost de produção.
7. **`X-Req-Id` até Martin**: nova `location /tiles/` em `deploy/nginx.conf` que gera/repassa
   `$request_id` como `X-Req-Id` a montante e loga o mesmo valor num access log PRÓPRIO
   (`deploy/nginx-log-formats.conf`, formato `plat_tiles`) — Martin não tem como logar cabeçalho
   arbitrário do próprio processo (CLI só tem `RUST_LOG`). TiTiler não existe hoje no `plat`
   (`PLAT_TITILER_URL` vazio; a porta 8152 é reservada, sem serviço) — mecanismo pronto, sem alvo para
   testar contra; cláusula parcial nomeada (docs/OBSERVABILIDADE.md §7).

## Alternativas descartadas

- Rotular métrica HTTP pelo slug do inquilino: mais legível num painel, mas rompe a regra binária de
  nunca vazar nome de cliente — rejeitado sem meio-termo.
- Usar `pg_stat_statements`/`stat_user_tables` sem filtro: cardinalidade medida em 231.807 séries só de
  tabelas de OUTRAS frentes no mesmo banco compartilhado — rejeitado.
- Confiar em Martin logar o `X-Req-Id` no próprio processo: a CLI (`martin --help`) não expõe formato
  de log de acesso configurável, só nível (`RUST_LOG`) — não dá para provar sem inventar recurso que o
  binário não tem.

## Consequências

- Toda métrica nova daqui em diante segue o mesmo contrato (§3-4 acima) — é o texto que
  `docs/OBSERVABILIDADE.md` grava para o próximo item que adicionar uma família.
- `plat_tiles_requisicoes_total` fica sem tráfego real até o item `L1-01-d-garage-por-inquilino` (COG
  por Range) ser mesclado em `master` — a família e o teste já existem, só falta o chamador.
- O Prometheus da casa (`/opt/monitoring/`, fora deste repositório) ganhou 6 *scrape jobs* novos,
  registrados só por acréscimo (nunca substituição) — ver docs/OBSERVABILIDADE.md §6 para o estado de
  cada alvo em 07/09/2026.
