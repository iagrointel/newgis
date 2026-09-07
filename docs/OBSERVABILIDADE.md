# Observabilidade (item L7-06-a-metricas-exporters)

Análise / beta privado. Este documento lista cada família de métrica exposta pela plataforma, o
exporter que a produz, o significado, os rótulos e o contrato de cardinalidade. Regra que vale para
TUDO neste documento e em qualquer métrica nova: **rótulo por inquilino é sempre `tenant`/`tenant_id`
= `plat.tenant.id` (inteiro opaco), nunca o slug** (o schema de dado `d_<slug>` pode carregar o nome
do cliente) **e nunca token/token_id/login/e-mail**. A ausência de um rótulo assim não é um limite de
implementação — é a garantia de que a rota de métricas nunca vaza nome de inquilino nem token, mesmo
que o número de tokens ou de pedidos cresça sem limite.

## 1. `GET /metrics` da API (`app/metricas.py`, plat-api :8150)

Não exige sessão nem token: a porta só escuta em `127.0.0.1` (unidade `plat-api.service`); o único
cliente é o Prometheus da casa, rodando na mesma máquina. Content-type `text/plain` do
`prometheus_client`.

| família | tipo | rótulos | significado |
|---|---|---|---|
| `plat_http_requests_total` | counter | `rota`, `status`, `tenant` | 1 requisição concluída. `rota` é o **padrão da rota casada pelo roteador** (`request.scope["route"].path`, ex. `/api/jobs/{job_id}`), nunca o caminho literal com o id do recurso — isso é o que mantém a cardinalidade limitada a (nº de rotas × nº de códigos de status × nº de inquilinos), e não a (nº de recursos × nº de pedidos). Requisição sem rota casada (404 de caminho arbitrário) usa `rota="outro"`. |
| `plat_http_request_duracao_segundos` | histogram | `rota` | Latência por padrão de rota (sem `tenant`: cruzar latência por inquilino é o painel "por inquilino" do item L7-06-d, calculado no Grafana a partir de `plat_http_requests_total` quando o volume justificar, não uma métrica nova). |
| `plat_tiles_requisicoes_total` | counter | `origem`, `resultado` | Requisições de ladrilho/COG que a **API** autoriza diretamente (ex.: verificação de token antes de servir um recorte). Hoje a família existe e está coberta por teste direto (`tests/unit/test_metricas.py`), mas **nenhuma rota de produção a incrementa ainda** — a autorização de COG por Range (item L1, `_cog/autorizar`) está em outro ramo, não mesclado em `master` no momento desta entrega (ver §5). Martin tem sua PRÓPRIA família nativa (§3) e não passa por aqui. |
| `plat_jobs_processados_total` | counter | `tipo`, `estado_final` | 1 job que TERMINOU de vez (`concluido`, `falhou` ou `cancelado` — nunca `pendente`, que é devolução para nova tentativa). Incrementada pelo **worker** (`app/jobs/worker.py::_finalizar` e o caminho de tipo não registrado em `_lancar`), não pela API. |
| `plat_jobs_fila` | gauge | `estado` (`pendente`\|`rodando`) | Fila agregada **entre todos os inquilinos** — vem de `plat.fila_estado()` (SECURITY DEFINER, já existia para `/saude`), consultada a cada scrape. Zero cardinalidade nova: a função nunca devolve por inquilino. |
| `plat_jobs_workers_vivos` | gauge | — | Nº de processos worker com heartbeat nos últimos 90s (mesma fonte). |

`plat_jobs_fila`/`plat_jobs_workers_vivos` só existem no processo da API (`app/saude.py` registra o
coletor uma única vez); o worker **não** duplica a consulta — abriria um segundo pool de conexões só
para repetir o que a API já expõe.

## 2. `GET /metrics` do worker (`app/jobs/worker.py`, plat-worker :8153)

Mesmo módulo `app/metricas.py`, processo separado (o worker não roda FastAPI — é um laço próprio com
um servidor HTTP mínimo por socket bruto, igual ao `/saude` já existente). Expõe **só**
`plat_jobs_processados_total` (o worker é quem sabe o resultado real de cada job) — sem
`plat_http_requests_total` (o worker não atende HTTP de cliente) nem o coletor de fila (ver acima).

## 3. Martin (nativo, plat-martin :8151)

Martin expõe suas próprias métricas em **`/_/metrics`** (não `/metrics` — conferido em 07/09/2026;
`/metrics` devolve 404 porque Martin interpreta o caminho como nome de fonte de tile). Família
principal: `martin_http_requests_duration_seconds` (histograma por `endpoint`, `method`, `status`).
Não precisou de nenhum código nosso — só o *scrape job* do Prometheus (`job_name: plat-martin`,
`metrics_path: /_/metrics`, ver §6).

## 4. node-exporter (:9100), Garage (:3903), postgres_exporter (:9187), nginx_exporter (:9113)

- **node-exporter**: já rodava (`iagro-node-exporter`, container, item anterior à casa) — só precisou
  do *scrape job* (já existia, aliás: `job_name: node-exporter` estava no `prometheus.yml` da casa).
- **Garage**: `/metrics` (admin API, :3903) já respondia sem token nesta instalação — decisão pendente
  do dono (§7 D-metrica-1): exigir `metrics_token` do Garage ou aceitar que só é alcançável de
  `127.0.0.1`, o que já é o caso hoje (a porta não é exposta por nginx nem por DNS).
- **postgres_exporter** (`prometheus-postgres-exporter` 0.15.0, apt): role dedicada `plat_metrica_pg`
  (só `GRANT pg_monitor` + `SELECT` em `plat.tenant`, nunca dono de nada, nunca em nenhum schema
  `d_<slug>`), senha em `/etc/plat/segredos/PLAT_METRICA_PG_SENHA` (600, root). Duas famílias
  PRÓPRIAS (`deploy/postgres_exporter_queries.yaml`), as duas de baixo risco de cardinalidade:
  - `plat_tenant_schema_bytes{tenant_id}` — soma de `pg_total_relation_size` das tabelas do schema
    `d_<slug>` do inquilino, agrupada por `tenant_id` (nunca o schema/slug em si).
  - `plat_tenant_conexoes{tenant_id}` — conexões abertas AGORA com aquele contexto, lidas de
    `pg_stat_activity.application_name = 'plat:<tenant_id>'` (novo: `app/db.py::_preparar` agora seta
    `application_name` por conexão — é o ÚNICO jeito de uma sessão externa (o exporter) enxergar o
    inquilino de OUTRA sessão, porque `current_setting('plat.tenant_id')` só lê a própria).
  ⚠️ **Os coletores padrão `stat_user_tables`/`statio_user_tables` foram DESLIGADOS de propósito**
  (`--no-collector.stat_user_tables --no-collector.statio_user_tables`): medido em 07/09/2026, ligados
  eles devolviam **231.807 séries** — o `iagro_sat` é compartilhado por dezenas de frentes da casa (não
  só o `plat`) e o scraper varre TODAS as tabelas visíveis ao papel, de qualquer schema. Isso não é
  métrica nossa e estouraria a cardinalidade do Prometheus da casa por engano. ⚠️ **Achado real, mesmo
  dia**: sem `statement_timeout`/`lock_timeout` no papel, uma DDL concorrente de outra trilha (`CREATE
  SCHEMA`/migração) prendeu 7 scrapes em `Lock/relation` por até 4 minutos — a role tem os dois setados
  em 4s/2s (`ALTER ROLE ... SET`), então um scrape sob contenção falha rápido em vez de empilhar.
- **nginx_exporter** (`prometheus-nginx-exporter` 1.1.0, apt): aponta para um `stub_status` interno
  em `127.0.0.1:8096` (`deploy/nginx-metricas.conf`, arquivo PRÓPRIO em `sites-available`/`sites-enabled`
  — nunca editado dentro de `plat.iagrointel.com` nem de qualquer outro vhost da casa), `allow
  127.0.0.1; deny all;`.

## 5. `plat_tiles_requisicoes_total` — o que falta e por quê

A família e a função `app.metricas.registrar_tile` existem e têm teste unitário direto, mas **nenhuma
rota de `master` a chama hoje**: a autorização de COG por Range HTTP (`_cog/autorizar`,
`app/objetos_raster.py`) é do item `L1-01-d-garage-por-inquilino`, que na data desta entrega
(07/09/2026) vive só no ramo `wt/garage`/`fila/integra`, ainda não mesclado em `master`. Quando esse
código chegar a `master`, a integração é uma linha (`metricas.registrar_tile("cog_autorizar",
"autorizado"|"negado")` no ponto de decisão) — não uma família nova. Registrado como **cláusula
parcial** deste item (ver `laco/handoffs/T.../L7-06-a-metricas-exporters/99_veredito.md`).

## 6. Prometheus da casa (`/opt/monitoring/prometheus/prometheus.yml`)

Container `iagro-prometheus` (`network_mode: host`), config em `/opt/monitoring/prometheus/`. Os
*scrape jobs* deste item foram ACRESCENTADOS ao arquivo que já existia (nunca substituído):

| job | alvo | scrape em 07/09/2026 |
|---|---|---|
| `plat-api` | `localhost:8150/metrics` | `down` (404) — `plat-api.service` em produção ainda roda o `master` de antes deste item; fica `up` no próximo `install.sh`/restart depois do merge. |
| `plat-worker` | `localhost:8153/metrics` | idem (`plat-worker.service`) |
| `plat-martin` | `localhost:8151/_/metrics` | `up` |
| `plat-postgres-exporter` | `localhost:9187/metrics` | `up` |
| `plat-nginx-exporter` | `localhost:9113/metrics` | `up` |
| `plat-garage` | `localhost:3903/metrics` | `up` |

⚠️ **Achado sobre a máquina, não sobre o item**: `sed -i` num arquivo montado por *bind mount* em um
container Docker troca o inode (renomeia por baixo) e o container fica preso no conteúdo de ANTES da
edição até reiniciar — `docker restart iagro-prometheus` resolveu; `curl -X POST .../-/reload` sozinho
NÃO detecta a troca de inode. Editar esse arquivo específico sempre com algo que escreva no MESMO
inode (`tee`, `>>`) ou reiniciar o container depois de qualquer `sed -i`.

## 7. `X-Req-Id` até Martin/TiTiler

- **Martin**: `location /tiles/` nova em `deploy/nginx.conf` (contrato de URL já documentado em
  `laco/decomposicao/L2_CONCEITO.md`: `/tiles/{token}/{camada}/{z}/{x}/{y}` — proxy direto, a validação
  do token é dentro da função SQL, não no nginx). Martin **não tem como** logar um cabeçalho arbitrário
  do próprio processo (a CLI só oferece `RUST_LOG`, sem formato de log de acesso configurável) — por
  isso o rastro fica em `/var/log/nginx/plat_tiles_access.log` (`deploy/nginx-log-formats.conf`,
  formato `plat_tiles`, campo `req_id=$request_id`), que é exatamente o valor que o nginx manda a
  montante em `X-Req-Id`; o mesmo valor volta ao cliente na resposta (`add_header X-Req-Id
  $request_id`, igual ao que a API já faz). Provado em produção 07/09/2026: `HEAD
  /tiles/catalog` → `X-Req-Id: 78ca6e9d...` na resposta E a MESMA string na linha do
  `plat_tiles_access.log`.
- **TiTiler**: **não existe hoje um TiTiler do `plat`** — `PLAT_TITILER_URL` está vazio no `.env` de
  produção e `ARQUITETURA.md` já registrava a porta 8152 como reservada, sem serviço (o
  `plataforma-titiler` que roda em `:8131` é de OUTRO produto — "PLATAFORMA prova", não pode ser
  tocado, ver `CLAUDE.md`/skill "nunca se tocam"). Esta cláusula fica **parcial, nomeada**: o mecanismo
  (location + log format) está pronto e é o MESMO que serviria o TiTiler do `plat` quando ele nascer
  (troca só o `proxy_pass`); não há hoje o que testar de verdade.

## 8. Achado fora do escopo deste item (registrado, não corrigido aqui)

`GET /catalog` do Martin (ex.: `https://plat.iagrointel.com/tiles/../catalog` hoje só acessível direto
em `127.0.0.1:8151`, sem rota pública ainda) devolve a descrição de cada fonte como
`"<schema>.<tabela>"` — ex. `"d_demo.t_2301880233611dd4"`. Em produção, `d_<slug>` é o schema de dado
do inquilino: **isso vaza o slug do cliente para quem alcançar `/catalog`**. Não é uma métrica (por
isso não é cláusula deste item) e a rota pública de tiles ainda não existe (§7), mas fica registrado
aqui porque toca a mesma regra binária ("nunca vazar nome de inquilino") — quem entregar a rota
pública de tiles (`L2-01-b`/`L2-04`) precisa decidir: descrição genérica, ou `/catalog` exige o mesmo
token da própria camada.

## 9. Cardinalidade — o que foi medido

`tests/api/test_metricas_rota.py`:
- 50 inquilinos sintéticos, 1 pedido cada em `/api/eu`: `plat_http_requests_total` ganha exatamente
  as 50 séries novas esperadas (uma por inquilino), total de séries da família continua ≤ 5.000.
- Refutação: 10 inquilinos × 50 tokens (500 tokens no total, cada um usado 1 vez e apagado em
  seguida — o produto já limita 20 tokens ATIVOS por usuário, política alheia a este item) na MESMA
  rota: a métrica ganha **10** séries novas, nunca 500 — a cardinalidade segue o nº de inquilinos, não
  o de tokens. Nenhum dos 500 valores de token aparece no corpo de `/metrics`.
- `plat_jobs_fila{estado="pendente"}` não é número fixo: criar 1 job de verdade move o gauge em +1 na
  mesma rodada de teste.

## 10. Onde estão as senhas e os arquivos

| item | caminho | modo |
|---|---|---|
| senha de `plat_metrica_pg` | `/etc/plat/segredos/PLAT_METRICA_PG_SENHA` | 600, root |
| consultas do postgres_exporter | `/etc/plat/postgres_exporter_queries.yaml` (`deploy/postgres_exporter_queries.yaml` no repo) | 644 |
| env do postgres_exporter | `/etc/default/prometheus-postgres-exporter` | 600 (tem a senha) |
| vhost do stub_status | `/etc/nginx/sites-available/plat-metricas-nginx` (`deploy/nginx-metricas.conf`) | 644 |
| env do nginx_exporter | `/etc/default/prometheus-nginx-exporter` | 644 |
| formato de log `plat_tiles` | `/etc/nginx/conf.d/plat_log_formats.conf` (`deploy/nginx-log-formats.conf`) | 644 |
| log de acesso de `/tiles/` | `/var/log/nginx/plat_tiles_access.log` | padrão do nginx |
| scrape jobs da casa | `/opt/monitoring/prometheus/prometheus.yml` (fora do repositório — infra da casa, nunca substituído, só acrescentado) | — |
