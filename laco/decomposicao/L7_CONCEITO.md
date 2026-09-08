# L7 operação e produção — decisões de conceito (05/09/2026)

Linha L7 do laço PLATAFORMA ENTERPRISE. Este documento reúne as decisões que, se erradas, obrigam a refazer trabalho
de outras linhas. Cada decisão traz: opções, o que custa mudar depois, recomendação com motivo MEDIDO nesta máquina
ou LIDO em documento oficial (URL testada por HTTP em 05/09/2026; a lista completa com o que cada página diz está em
`L7.json` → `fontes`), e o que a decisão obriga nas outras linhas. Itens: `L7.json` (60 novos, 13 existentes na linha;
2 dependências externas propostas: L2-04-b parser do where por AST e L2-01-a mapa-base local em PMTiles; as de eventos e lixeira já existem na L0). Regras herdadas: análise/beta privado; sem nome de cliente; sem preço Esri; número
só de medição ou de documento.

## 0. O que já existe e é reaproveitado (medido 05/09/2026)

| Ativo | Onde | O que dá de graça para a L7 |
|---|---|---|
| Prometheus v2.54.1 + Grafana 11.2.0 + node-exporter v1.8.2 | `/opt/monitoring` (docker compose, host network, 127.0.0.1:9090 / :3000 / :9100), retenção 15 d, 0 regras de alerta, 1 painel; scrape da API da casa em :8002 que já expõe `/metrics` com `prometheus_client` | L7-06 acrescenta jobs de scrape e painéis provisionados; não instala outro Prometheus no hospedado |
| Garage 2.x com admin API | `plataforma-garage` :3900 (S3), :3903 (admin, `/metrics` responde 200), `replication_factor = 1`, `admin_token` e `rpc_secret` em claro em `pipeline/garage/garage.toml` | métricas prontas; L7-19 tira os segredos do arquivo; L7-07-b sobe rf=2 |
| nginx 1.24 com `proxy_cache_path plataforma_tiles` (3 GB, 14 d), `proxy_cache_lock`, `slice 1m` para COG, `X-Cache`, zonas `limit_req` `perip` 100 r/min e `authip` 10 r/min, ModSecurity com OWASP CRS em `/etc/modsecurity/crs` (desligado por `location` na prova) | `/etc/nginx/sites-enabled/iagrosat-db` linhas 290-340, `conf.d/plataforma-cache.conf`, `nginx.conf` 42-44 | cache de tiles e de range medido (36-56 ms frio, 8,7 ms quente, 20 pedidos ao mesmo tile frio = 1 MISS + 19 HIT); WAF disponível para L7-03 |
| fail2ban 1.0.2 (3 jails: nginx-botsearch, nginx-limit-req, sshd), unattended-upgrades (security), certbot.timer | sistema | L7-03-b acrescenta jail própria; certificados renovam sozinhos |
| PostgreSQL 16.13 + PostGIS 3.6.3: `wal_level=replica`, `archive_mode=off`, 0 réplicas, `ssl=on`, `scram-sha-256`, `shared_preload_libraries = timescaledb, pg_cron, pgaudit`, `log_min_duration_statement = 5 s`, `max_connections = 100`, banco `iagro_sat` = 543 GB, `/mnt/pgdata` com 17 GB livres | `sudo -u postgres psql` | pgaudit e pg_cron já carregados (L7-20, L7-12-a, L7-32); o físico com PITR NÃO cabe neste disco (decisão C3) |
| Backups lógicos por schema com timer e drill | três timers systemd de backup dos SIGs de teste da casa (03:15, 03:35 e 03:45); scripts `backup.sh`/`restore_test.sh` do SIG de teste interno (pg_dump -Fc, sha256, tabela `backup`, restore em banco temporário com contagem); backup diário do servidor DESLIGADO em 27/05/2026 por disco cheio | padrão da fase 1 (L0-06-a) e do drill (L7-24) |
| Log JSON com `X-Req-Id` e `plat.log_acesso` com RLS | `app/log.py`, `app/main.py`, migração 002 | base do L7-06-c |
| `install.sh` idempotente medido (do zero 6,2 s; nunca-viu 9,1 s; repetido 4,7 s), `db/migrar.sh` com sha256 e imutabilidade, `make check` (ruff + sem-marcador + pytest 57 + e2e 1) | repositório `plataforma/enterprise` | base de L7-01/L7-35 (atualização); o adversário T1 já apontou: pacotes vindos de `~/.local`, senha em argv do sudo no journal, `mv` antes de `nginx -t`, Swagger UI de CDN, sem HSTS |
| `bench_conc.py` (threads + requests, quente × frio, X-Cache) | `plataforma/pipeline/` | L7-02 troca por k6 mas mantém as mesmas URLs e a comparação |
| docker 29.1.3, node 22, playwright chromium, tippecanoe | sistema | compose (L7-01-a), e2e, PMTiles |
| apt (candidatos, sem instalar): pgbackrest 2.59.1, clamav 1.5.3, prometheus-postgres-exporter 0.15.0, prometheus-nginx-exporter 1.1.0, prometheus-alertmanager 0.26.0, prometheus-blackbox-exporter 0.24.0, postgresql-16-pgaudit 16.1, pgbouncer 1.25.2 | `apt-cache policy` | k6 e trivy NÃO estão no apt (binário do GitHub) |
| Python do sistema: fastapi 0.138, uvicorn 0.27, psycopg2 2.9.9, httpx 0.28, babel 2.10.3; AUSENTES: prometheus_client, pyotp, slowapi, argon2, clamd | `python3 -c import` | requirements do L7 têm de listar os ausentes (lição do adversário T1) |
| Este servidor é `iagrosat-db-sp` (Vultr São Paulo); iagrointel.com passa pela Cloudflare (PoP GRU); `plat.iagrointel.com` é DNS-only (D19) | `05_CDN.md`, `hostname` | perfil BR já existe de fato; CDN de tiles precisa de hostname separado (C9) |

## C1. Unidade de implantação: um repositório, dois empacotamentos, um único caminho de migração

Opções: (a) só `install.sh` + systemd (o que existe); (b) só docker compose; (c) os dois, gerados dos mesmos arquivos,
com perfis `hospedado` e `appliance`.

Custo de mudar depois: alto. Cada serviço novo (Martin, TiTiler, worker, Keycloak opcional) nasce com unidade systemd
E serviço do compose; se uma linha entregar só um dos dois, o appliance (L7-11) e a instalação limpa (L7-01) reprovam
juntos, e o esquema do banco pode divergir entre os caminhos.

Recomendação: (c). MEDIDO: o `install.sh` do zero leva 6,2-9,1 s e já é idempotente (tests/medidas/L0-01-repo.json);
jogar isso fora não faz sentido. LIDO: o compose file suporta `profiles`, `healthcheck`, `secrets` (DOCKER-compose-file);
o GeoServer e o QGIS Server publicam checklist de produção em contêiner (GS-production, QGIS-server-config) — o cliente
que hoje roda Enterprise espera receber "um pacote que sobe". Regra: as migrações (`db/migracoes`) e a semeadura são o
ÚNICO lugar de esquema; os dois empacotamentos só chamam `migrar.sh`. Teste que fecha: `pg_dump -s` dos dois caminhos
com diff vazio (L7-01-a).

Obriga: toda linha que cria serviço entrega `deploy/<serviço>.service` E `deploy/compose/<serviço>.yml` no mesmo
turno; nenhuma dependência Python fora de `requirements.txt` (P5 já exige; o adversário T1 pegou fastapi vindo de
`~/.local`); dado de demonstração (L7-01-c) é o único dado que instaladores semeiam.

## C2. Versão, pacote e atualização: semver em `VERSAO`, pacote assinado ed25519, migração só para frente

Opções de atualização: (a) `git pull` + `migrar.sh` + restart (o que o laço faz hoje); (b) pacote tar + manifesto
sha256 + assinatura verificada offline; (c) imagens de contêiner assinadas com cosign.

Custo de mudar depois: médio-alto — o appliance vive sem internet e sem git; se a atualização depender de git ou de
verificação em rede (cosign keyless), o L7-11 reprova.

Recomendação: (b) para os dois empacotamentos, com (c) opcional para quem roda registry próprio. LIDO: cosign em modo
keyless precisa de Fulcio/Rekor na rede (COSIGN); ed25519 verifica offline. LIDO (Esri): atualização de versão segue
ordem Portal → Server → Data Store e o `patchnotification` lê um JSON público de patches (E11-upgrade-portal,
E11-upgrade-server, E11-patch); em HA "nunca as duas máquinas ao mesmo tempo" (E11-ha-patch). Regras:
- `VERSAO` semver 2.0.0; etiqueta `vX.Y.Z` assinada; CHANGELOG no formato keep-a-changelog gerado (SEMVER, CHANGELOG).
- Migrações IMUTÁVEIS e só para frente (já é assim em `migrar.sh`); mudança de esquema segue expandir/contrair: a
  versão N acrescenta coluna/tabela e o código lê os dois; a N+1 remove o antigo. Rollback = código anterior +
  restauração do dump lógico feito pelo próprio `plat atualizar` antes de migrar. Não existe "migração para baixo".
- Atualização entra em modo somente-leitura (C11) e reinicia serviços um a um.
- Homologação obrigatória com o MESMO sha antes de produção (L7-15, L7-31).

Obriga: toda linha escreve migração compatível com a versão anterior do código por uma versão (expandir/contrair);
nenhuma linha muda o formato de `VERSAO` nem o nome dos arquivos de migração; toda dependência JS vendorizada tem
versão e sha256 em `web/vendor/VERSOES.txt` (o pacote assinado inclui `web/`).

## C3. Backup: duas camadas com escopos diferentes, e o SLA de RPO só onde o cluster é dedicado

Opções: (a) só dump lógico por schema (padrão da casa hoje); (b) pgBackRest do cluster inteiro com WAL contínuo (PITR);
(c) instância Postgres própria do plat (porta 5433) para poder fazer (b) sem tocar nos outros projetos.

Custo de mudar depois: alto para o SLA — o RPO de 15 min da spec 17.4 e o RTO de 8 h só existem com WAL arquivado e
réplica; se a linha prometer isso sem (b), o L7-22 e o L7-07 reprovam.

Fatos MEDIDOS: `iagro_sat` tem 543 GB de vários projetos; `/mnt/pgdata` tem 17 GB livres; `archive_mode=off`; ligar
`archive_mode` exige reinício do Postgres compartilhado (decisão do gerente/dono; a L0 registrou o mesmo em D15).
LIDO: pgBackRest opera por cluster (`pg1-path`), repo S3-compatível, retenção por full, PITR, delta restore
(PGBR-guide); Garage é S3-compatível (GARAGE-s3); B2 não tem região na América do Sul (B2-regions). LIDO (Esri): o
webgisdr faz full/incremental e o incremental exige PITR ligado no relational data store (E11-webgisdr); a tabela
"parada aceitável × perda aceitável" mostra que backup diário = ~1 dia de cada (E11-perda-x-parada).

Recomendação: as duas camadas, com escopo declarado:
1. LÓGICO por inquilino (L0-06-a/L0-06-d, drill L7-24): sempre, nos dois empacotamentos; é o escrow e a exportação
   em formato aberto. RPO = 24 h (dump diário). É o que este servidor consegue hoje.
2. FÍSICO com PITR (L7-23, pgBackRest): obrigatório onde o cluster é só do plat — appliance (compose traz o Postgres) e
   a 2ª máquina da spec; neste servidor compartilhado só com repositório fora da máquina e decisão do dono (D21).
   RPO = intervalo de `archive_timeout` (medido no drill), RTO do backup = medido; RTO de horas vem da réplica (C4).
Alternativa (c) fica registrada: resolve o escopo mas custa RAM (3 GB disponíveis) e uma segunda instância para
operar; só se o dono negar (b) no compartilhado.

Regra dura: `docs/SLA.md` declara RPO/RTO por PERFIL de instalação (compartilhado / dedicado / appliance) e só com
número de `tests/medidas/`. "Restore drill mensal publicado" vale para as duas camadas.

Obriga: L0-06-a grava `plat.backup` com sha256 (já previsto); toda tabela de dado do inquilino fica em schema ou
bucket que o dump por inquilino alcança (L0 D13/D15: `d_<slug>` e bucket por inquilino); L1 nomeia objeto por sha256
(imutável, o backup incremental do bucket é por listagem); L2-13 (versionamento) não pode guardar estado fora do banco
e do bucket.

## C4. Alta disponibilidade: réplica em streaming + failover MANUAL assumido; Patroni só com 3 nós

Opções: (a) uma máquina, backup só (RTO dias); (b) réplica física assíncrona + `pg_promote` por script + troca de
DNS/IP + Garage rf=2 (failover manual, minutos a horas); (c) Patroni/etcd com failover automático (exige 3 nós de DCS).

Custo de mudar depois: médio — a réplica e o script de promoção são reaproveitados em (c); o que muda é o DCS e o
balanceador.

Recomendação: (b) enquanto houver 2 máquinas (spec 17.2/18: 2ª máquina entra por réplica, não por disco). LIDO
(Esri): HA = duas cópias ativas + balanceador de terceiros com failover automático e um "componente humano" (admin
disponível; patch nunca nos dois ao mesmo tempo) (E11-ha); no Server de uma máquina, ativo-passivo são dois sites
independentes atrás do balanceador (E11-ha-1maq); DR desconectado = export/import periódico (E11-dr). LIDO (Postgres):
hot standby e streaming têm janela de perda pequena; síncrono custa latência (PG-standby). Patroni LIDO e adiado.
O SLA vendável (17.4, 01_SERVIDORES §6): 99,5 % mensal com crédito SÓ com a 2ª máquina; sem ela, sem crédito.

Obriga: leitura roteável para a réplica (`PLAT_DSN_LEITURA`) — as linhas L1/L2 não podem escrever em rota de leitura
(tiles, query) nem depender de `SELECT ... FOR UPDATE` nelas; L1 objetos no Garage com rf ≥ 2 quando houver 2 nós;
nenhum estado em disco local do serviço (sessão, fila, cache que importe) — tudo no Postgres/Garage.

## C5. Eventos de domínio: `plat.evento` (L0-10) é a única origem de webhook, trilha, medição e laço agêntico

Opções: (a) cada consumidor instrumenta as rotas (webhook aqui, auditoria ali); (b) tabela de eventos escrita na
mesma transação da mudança (outbox), consumida pelo worker.

Custo de mudar depois: muito alto — é modelo de dado; a L0 já decidiu (L0-10-eventos-historico: append-only, RLS,
escrita por função SECURITY DEFINER, vocabulário fechado espelhando os gatilhos da Esri, particionada por mês).

Recomendação: (b), adotando o L0-10 como está. LIDO (Esri): webhooks de organização (items/users/groups/roles) e de
serviço (FeaturesCreated/Updated/Deleted/Posted), receptor só HTTPS, payload com `when`, `operation`, `source`, `id`,
`properties` (E11-webhooks, E11-webhook-payload); retentativa 1-5 tentativas, 5 s entre tentativas por padrão, política
de desativação por falhas numa janela de dias (REST-server-webhook-settings). Formato de entrega: cabeçalhos Standard
Webhooks (`webhook-id`, `webhook-timestamp`, `webhook-signature` HMAC-SHA256) (STDWEBHOOKS) e corpo com os nomes de
campo da Esri para facilitar quem migra. Idempotência pelo id do evento. Payload NUNCA leva atributo de negócio
(só ids): o receptor busca pela API — isso fecha vazamento por webhook de camada `pessoal` (C12).

Obriga: L2-03/L2-04 (edição) emitem evento por feição alterada com id da camada e da feição; L0-05 (jobs) emite
`job.concluido/falhou`; L4 emite `rede.tracado.concluido`; L5-02 (fluxos) aceita evento como gatilho; nenhuma linha
escreve em `plat.evento` fora da função da L0.

## C6. Observabilidade: Prometheus/Grafana da casa no hospedado, os mesmos arquivos no appliance; métrica com rótulo `tenant`, nunca `token`

Opções: (a) pilha própria do plat separada; (b) acrescentar ao `/opt/monitoring` existente; (c) SaaS.

Custo de mudar depois: baixo para métricas (nomes e rótulos são o contrato), alto se a cardinalidade explodir
(séries por token = milhões).

Recomendação: (b) no hospedado (não há por que dois Prometheus na mesma máquina de 23 GB) e perfil `observabilidade`
do compose no appliance com os MESMOS `deploy/alertas.yml` e `deploy/grafana/*.json`. Contrato de métrica:
prefixo `plat_`, histograma de latência por rota (não por URL), contadores por `tenant` (dezenas a centenas de
valores), NUNCA por token nem por item (esses vão para `plat.uso_diario`, C7). LIDO (Esri): ArcGIS Monitor é produto
separado com alertas por limiar e relatórios (E11-monitor); o Server guarda estatísticas com `samplingInterval` (30 min
no exemplo) e `maxHistory` em dias (REST-server-usage-settings); logs com níveis OFF…DEBUG, padrão WARNING, retenção
`maxLogFileAge` 90 dias (REST-server-editlog). Aqui: níveis ajustáveis em runtime por rota, retenção 90 d, `req_id`
propagado (`X-Req-Id` já existe; passa a ir para Martin/TiTiler e como `application_name` no Postgres). Alertas:
Alertmanager (apt) ou alerting do Grafana — decidido no L7-06-b pela simplicidade do appliance; as REGRAS são as mesmas.
Página de status: dados do Prometheus + `plat.disponibilidade_mensal` persistida (a retenção da casa é 15 d; 12 meses
exigem persistir). Rastreamento distribuído (OTel) fica para fase 2.

Obriga: toda rota nova nasce com histograma (o middleware faz isso sozinho se a rota tiver `operationId`); todo
serviço novo (Martin, TiTiler, worker) expõe `/metrics` e propaga `X-Req-Id`; nenhuma linha registra métrica com
rótulo de alta cardinalidade.

## C7. Medição e cobrança: `plat.uso_diario` com o comando de conferência na linha; tiles contados na ORIGEM

Opções de contagem de tiles: (a) na API (não vê HIT do nginx nem da CDN); (b) no log de acesso do nginx (vê HIT/MISS
da origem; não vê HIT da CDN); (c) na CDN (analytics/log da Cloudflare ou Bunny).

Custo de mudar depois: médio — muda a fonte, não a tabela.

Recomendação: (b) como fonte de verdade da cobrança (o que a origem serviu), (c) como informação quando existir,
marcada `nao_medido` quando não. Motivo MEDIDO: com cache quente 1.080 tiles/s por cliente não chegam à API; só o
nginx vê. LIDO (Esri): usage reports do Portal (Activity Dashboard) e estatísticas do Server (E11-usage, E11-stats,
REST-server-usage). Modelo de plano: `plat.plano` (limites e preço de lista por região; o preço é D4 do dono) e aplicação
de limite: aviso 80 %, bloqueio de ESCRITA em 100 %, leitura e exportação nunca bloqueadas (o dado é do cliente).
Toda linha de `plat.uso_diario` guarda o comando que a produziu (`du`, `pg_total_relation_size`, `wc -l` do log),
para o adversário conferir (refutação do L7-09: "compara TB medido com du do bucket").

Obriga: L1-02 escreve o token no log do nginx em campo próprio (formato JSON de log de acesso) e nomeia bucket/objeto
por inquilino; L0-07 (cotas) usa `plat.uso_diario`, não conta por conta própria; L0-05 registra CPU-s e GPU-s por job.

## C8. Segurança: ASVS 5.0 L2 como régua, token no caminho, consulta por AST, upload por pipeline único

Decisões que valem para todas as linhas (o L7-03 só testa; quem constrói é quem cumpre):
- Régua: OWASP ASVS 5.0 nível 2 (estável desde 30/05/2025; ASVS-rel), checklist em `docs/asvs.yaml` com evidência por
  requisito. Paridade com a Esri: `serverScan.py` gera relatório HTML de boas práticas (E11-scan); o Server traz CSP
  padrão `script-src 'self';`, nosniff, `standardizedQueries=true`, `featureServiceXSSFilter=input`, lista de extensões
  de upload (REST-server-secconfig, REST-server-props). A régua aqui é superar isso e provar por teste.
- Token/chave: no caminho para tiles (spec, 05_CDN §6) e em cabeçalho `Authorization` para API (a Esri recomenda
  `X-Esri-Authorization` em vez de query para não vazar em proxy; E11-sec-bp); escopos nomeados, expiração obrigatória
  (Esri: token máx. 14 d; chaves de API com expiração — DEV-apikey), revogação em ≤ 5 s.
- Consulta: `where`/CQL2 por parser → AST → SQL parametrizado (dependência externa proposta L2-04-b); identificador
  sempre por `psycopg2.sql.Identifier`. Sem isso o FeatureServer não vai a produção.
- Upload: um pipeline (`app/upload.py`) para tudo — tamanho por plano, tipo por bytes mágicos, lista por rota, nome
  reescrito por id, SVG sanitizado, zip-bomb, anexo servido com CSP `sandbox` e `Content-Disposition`, ClamAV
  opcional com quarentena (a L0-04-a já deixa o estado `em quarentena`).
- SSRF: `url_segura()` única para toda URL de usuário (conectores, webhooks, STAC, imagem por URL); rede privada,
  metadados, esquemas e portas fora da lista recusados; re-resolução após redirecionamento.
- Cabeçalhos: HSTS, CSP com nonce e `script-src 'self'` (Swagger/portal de API vendorizados), `frame-ancestors` por
  inquilino (embutir app no site do cliente é caso de uso), COOP/CORP, Permissions-Policy; TLS perfil intermediate.
- Segredos: `LoadCredential=` do systemd (Ubuntu 24.04) e `secrets:` do compose; `.env` sem segredo; rotação com dupla
  chave; nunca segredo em argv (o adversário T1 achou a senha de demonstração no journal).
- Trilha: `plat.auditoria` append-only (distinta de `plat.evento`: a trilha guarda quem/quando/o quê para pessoas e
  SIEM; o evento é para máquinas) + pgaudit para DDL (E11-audit).

Custo de mudar depois: alto em token (URLs coladas em web maps duram meses) e em parser (reescrever o FeatureServer).

Obriga: L0-02 (escopos, expiração, revogação ≤ 5 s), L1-02 (token no caminho, Referer/IP), L2-04 (parser), L0-04/L1-01/
L2-03/L2-07 (upload pelo pipeline único), L6-02/L1-03 (`url_segura()`), L5 (CSP com nonce: os construtores não podem
gerar `onclick=` inline), L0-09/L2-12 (PDF/impressão sem executar conteúdo do usuário).

## C9. CDN e cache: hostname separado e proxied para tiles; versão no caminho; app fora da CDN; gatilho de 1 TB/mês

Opções: (a) tudo pela Cloudflare (proxied) — conflita com D19 (app DNS-only) e com o ToS para arquivo grande vindo de
origem externa; (b) hostname de tiles proxied + app DNS-only; (c) Bunny/R2 desde o início.

Custo de mudar depois: baixo se a URL de tile já tiver versão no caminho (purge zero) e o hostname for próprio (troca
de CDN = troca de DNS); alto se o token ou a versão forem query string (chave de cache e ToS).

Recomendação: (b) agora, com regra escrita de saída para (c). LIDO: Cache Rules Free = 10 regras (CF-rules); purge por
prefixo com 100 prefixos por pedido (CF-purge-prefix); a Cloudflare não guarda 206 e o COG não cabe no cache
(05_CDN §4) → range de COG fica no cache `slice` do nginx (já configurado, NGINX-slice); ToS: arquivo grande de origem
externa é restrito fora do Enterprise (05_CDN §2) → acima de ~1 TB/mês, Bunny (PoPs BR, HMAC nativo) ou R2 como
origem. Regional Services (terminação TLS e cache só na região) é do plano Enterprise (CF-regional) → para exigência de
solo, CDN desligada por inquilino (C10). URL: `/svc/<token>/<item>@<versao>/{z}/{x}/{y}`; objeto nomeado por sha256
(já é o padrão da prova) → `Cache-Control: public, max-age=31536000, immutable`; 404 curto fora da cobertura.

Obriga: L1-02 põe a versão no caminho e nunca em query; L2-01 monta a `source` do MapLibre com a URL de tiles do
hostname de CDN; L0-03 gera nova versão de item ao republicar (purge zero); L7-27 marca por inquilino "sem CDN".

## C10. Residência de dados: atributo da INSTALAÇÃO, não do inquilino; uma instalação por região

Opções: (a) campo `residencia` por inquilino roteando bucket/banco/backup dentro da mesma instalação; (b) uma
instalação por região (BR = este servidor Vultr São Paulo; EU = Hetzner), e o inquilino nasce numa delas.

Custo de mudar depois: (a) contamina toda consulta e todo job com roteamento por região e quebra o backup físico (um
cluster, várias regiões); (b) custa duplicar a operação (dois Prometheus, dois status), que já é automatizada.

Recomendação: (b). LIDO: Hetzner certificada ISO 27001 em todos os DCs (HETZNER-cert); B2 sem região na América do Sul
(B2-regions) → o repositório 2 do perfil BR é outro provedor com região BR ou Storage Box com cláusula; transferência
internacional exige cláusula (ANPD-transf, LGPD art. 33; spec D2). Documento por inquilino gerado da configuração real
(IPs, provedores, países, traceroute datado), nunca digitado. CDN só para camadas `publica/interna` (C12).

Obriga: L0-07 mostra a região da instalação na organização (só leitura); L6-02 (conectores) e L7-08-a (webhooks) avisam
quando o destino está fora da região; L1 nunca copia objeto entre instalações sem job explícito e trilha.

## C11. Modo somente-leitura como primitiva de operação

LIDO (Esri): `mode` do Portal coloca portal, servidores federados e data stores em somente-leitura (bloqueia POST e
admin; leitura continua) (REST-portal-mode); site mode `READ_ONLY` do Server bloqueia publicação e a maioria das
operações admin, reinicia serviços e copia a configuração local (REST-server-mode). Aqui: bandeira em `plat.sistema`
(global) e em `plat.tenant` (por inquilino) lida pelo middleware — escrita devolve 503 + `Retry-After` + Problem Details
(RFC9457, RFC9110); leitura, tiles e exportação continuam; jobs pausam. Usada por atualização (C2), failover (C4),
licença vencida (C13), manutenção. Custo de mudar depois: alto — é o que permite atualizar sem perder edição.

Obriga: toda rota de escrita passa pelo middleware (não há rota fora do FastAPI); FeatureServer/OGC/SDK respeitam o 503;
L0-05 pausa e retoma a fila sem perder job; o front mostra a faixa com o motivo (L2-01/L5-01).

## C12. Classificação de dado e retenção como atributo do catálogo; lixeira da L0

`item.classificacao` ∈ {publica, interna, pessoal, sensivel} e `campo.classificacao`; regras derivadas: `pessoal/sensivel`
nunca na CDN, nunca em exportação pública, nunca em payload de webhook, justificativa de acesso gravada na trilha,
mascaramento para `visualizador`; `reter_ate` + motivo, expurgo por pg_cron em dois passos (lixeira de 30 d da
L0-03-h, depois definitivo com evento). Registro das Operações de Tratamento (LGPD art. 37) gerado do catálogo; DPA
modelo; incidente conforme Resolução CD/ANPD 15/2024 (comunicação preliminar/completa/complementar; titulares em risco
relevante; `incidentes@anpd.gov.br`) (ANPD-incidente, ANPD-cis). A Esri não tem classificação por item nativa (não
encontrada na doc 11.4) — é diferencial de edital.

Custo de mudar depois: alto — a classificação entra na política de RLS de leitura e no roteamento de CDN.

Obriga: L0-03 tem as colunas desde a fundação (é uma migração, mas a política de leitura `pode_ler` da L0 D7 precisa
considerar a justificativa); L1-02/L7-26 leem a classificação antes de emitir URL de CDN; L0-06-d/L7-25 excluem
`pessoal` da exportação pública; L2-06 (painéis) e L5 (apps públicos) recusam camada `pessoal` em publicação anônima.

## C13. Licença do appliance: arquivo JSON assinado ed25519, sem telefonar para casa, vencida = somente-leitura

Opções: (a) chave em rede (licença verifica em servidor nosso); (b) arquivo assinado verificado offline; (c) sem licença
(contrato só).

Custo de mudar depois: médio (é um módulo), mas (a) reprova o appliance offline.

Recomendação: (b). LIDO (Esri): autorização por arquivo e recurso `licenses` no Portal (REST-portal-licenses); ambiente
desconectado exige desligar conteúdo externo e confiar na CA do cliente (E11-disconnected). Campos: inquilino,
validade, limites, módulos; aviso 30 d; vencida → C11; NUNCA bloqueia leitura nem exportação. Telemetria opt-in,
desligada por padrão, só agregados, texto do que sai mostrado antes de ligar.

Obriga: L7-16 (mesma raiz de chaves do pacote); L0-07 mostra a licença na organização; L2-01 tem mapa-base local
(dependência externa proposta L2-01-a, PMTiles) para o appliance não abrir cinza.

## C14. i18n e acessibilidade: chave de mensagem ICU em JSON por idioma; WCAG 2.1 AA como portão; mapa com equivalente textual

i18n: catálogos `web/i18n/{pt-BR,en,es}.json` no formato ICU (plural/gênero/número/data); `usuario.idioma` → inquilino →
pt-BR; troca sem recarregar (as cadeias são funções no módulo ES); servidor com Babel 2.10 (já instalado) para e-mail,
PDF e erro; `Accept-Language` na API. Dado do usuário nunca traduzido. LIDO (Esri): Manager em 10 idiomas incl.
português do Brasil e espanhol (E11-manager-lang); Portal com 42 códigos `esri_*` (REST-portal-languages, deprecado
desde 11.2 em favor de conteúdo por idioma). A L5-12 já entrega a base dos construtores; o L7-10 mede o produto inteiro.

Acessibilidade: WCAG 2.1 AA é o portão (WCAG21); critérios 2.2 adotados quando não custam (WCAG22 é a recomendação
vigente); eMAG 3.1 (abril/2014, especialização da WCAG para governo, CC BY 4.0 — EMAG) é a referência de edital e é
subconjunto. Mapa: navegação por teclado + lista "feições na vista" como equivalente textual. Medição por axe-core no
playwright em todas as telas; documento `docs/ACESSIBILIDADE.md` gerado no formato de ACR (a Esri publica ACR/VPAT por
produto: Enterprise 12.1 em 2026, Map Viewer jun/2025, Experience Builder fev/2026 — ESRI-vpat).

Custo de mudar depois: alto para i18n se algum construtor gravar texto fixo no HTML ou no JSON de app (a L5 já decidiu
chaves e rótulos multilíngues); médio para a11y.

Obriga: L2-01/L5 sem texto fixo fora do catálogo; toda tela com `data-ajuda`; L2-02 (simbologia) com contraste medido
nos padrões; L2-07 (campo) com alvos ≥ 44 px.

## C15. Ambientes e release: homologação na mesma máquina com banco separado; release por script com o mesmo sha

Homologação = unidade `plat-homolog` :8154, banco `plat_homolog` (CREATE DATABASE, não schema, para que migração,
backup e restore sejam idênticos aos de produção), bucket `homolog-*`, `homolog.plat.iagrointel.com` DNS-only com senha
básica, dado sintético. Release: `scripts/release.sh` (semver, changelog, etiqueta assinada, `make check` + e2e +
carga curta em homologação, pacote assinado, instalação em produção com o MESMO sha). Custo de mudar depois: baixo.
Motivo: 23 GB de RAM e 3 disponíveis — uma segunda máquina para homologação não existe; um banco separado custa só
disco (dado sintético é pequeno).

Obriga: toda linha entrega e2e que roda contra URL parametrizada (`--base-url`, já é assim no `conftest.py`); nenhuma
linha grava caminho absoluto de produção em código.

## C16. Suporte e laço agêntico: chamado com contexto automático; agente nunca escreve em produção

`plat.chamado` com RLS, captura automática + `req_id` das últimas requisições + versão + navegador; anexos pelo pipeline
de upload; ajuda por contexto ligada ao manual gerado (uma seção por tela com captura do próprio e2e). Laço agêntico
(spec 19): triagem por modelo aberto no GPU box, reprodução em HOMOLOGAÇÃO, proposta de diff com teste, humano nomeado
aprova, release normal (C15); regras: nunca escreve em produção, nunca vê dado de inquilino além do chamado, nunca
responde sem aprovação; horas humanas medidas por chamado (é o número da spec 19.2). Custo de mudar depois: baixo.

Obriga: toda tela expõe `data-ajuda` e `data-tela`; o front guarda os últimos 20 `X-Req-Id` para o formulário de
reporte; L0-07 define quem é "operador" (superadmin) versus admin do inquilino.

## C17. SLA, status e drill: número só de medição, persistido além da retenção do Prometheus

`docs/SLA.md` gerado por script; disponibilidade mensal = 1 − minutos com `up == 0` / minutos do mês, persistida em
`plat.disponibilidade_mensal`; RTO do ensaio de failover, RPO do WAL medido no drill; incidentes em `plat.incidente`
com post-mortem gerado; drill mensal por timer restaurando TUDO (não amostra) e comparando `COUNT(*)` de todas as
tabelas com `tenant_id` + sha256 de 1 % dos objetos com semente registrada. LIDO (Esri): "restore drill em cadência
semirregular" (E11-backup-bp); aqui é mensal e público. Custo de mudar depois: baixo.

Obriga: nenhuma linha escreve número de disponibilidade, RTO ou RPO em documento; tudo vem de `tests/medidas/` ou
das tabelas; a L0-06-e (status) é a base e o L7-21 acrescenta 12 meses e incidentes.

## C18. Paridade com ArcGIS Pro/AGOL: pendente até o teste do parceiro (D20)

Toda linha de `docs/PARIDADE.md` que fale de Pro/AGOL fica `pendente` até o formulário de resultado do parceiro
(protocolo `docs/TESTE_PARCEIRO.md`, L7-30). Nenhuma tela, manual ou roteiro de demonstração afirma "funciona no Pro"
sem data de teste. Custo de mudar depois: reputacional.

## O que a L7 pede às outras linhas (resumo das obrigações)

| Linha | Obrigação |
|---|---|
| L0 | `plat.evento` (L0-10) como único outbox; `plat.backup` com sha256; classificação/retenção nas colunas do catálogo (C12); escopos e expiração de token (C8); status base (L0-06-e); lixeira (L0-03-h); leitura roteável para réplica |
| L1 | versão no caminho do tile, objeto por sha256, token no log do nginx, classificação antes de emitir URL de CDN; `/metrics` e `X-Req-Id` no TiTiler; rf ≥ 2 no Garage com 2 nós |
| L2 | parser `where`/CQL2 por AST (L2-04-b, proposto); upload pelo pipeline único; sem texto fixo; `frame-ancestors` por inquilino; mapa-base local em PMTiles (L2-01-a, proposto); FeatureServer/OGC respeitam o 503 do modo somente-leitura |
| L3 | RLS em `amc_*` testada pelo L7-03 (a L3L6 já pede); resultados exportáveis no pacote do inquilino |
| L4 | evento `rede.tracado.concluido`; traçado longo como job pausável |
| L5 | CSP com nonce (sem `onclick` inline); chaves i18n e rótulos multilíngues (L5-12); apps públicos recusam camada `pessoal`; exportação estática para o appliance |
| L6 | `url_segura()` em todo conector; aviso de destino fora da região; extensões FDW pelo L7-14 |

## Fontes

208 URLs testadas por HTTP em 05/09/2026, listadas em `L7.json` → `fontes` com o que cada uma diz. Armadilhas
encontradas: `enterprise.arcgis.com/en/*/latest/` redireciona para `doc.esri.com/.../latest/` = 12.1; a série 11.4
versionada responde 200 sem redirecionamento e é a usada; nomes de página adivinhados devolvem 404 (usar os sitemaps
`.../11.4/administer/windows/sitemap.xml`, 289 páginas do Portal e 194 do Server); `developers.arcgis.com` é renderizado
por JavaScript (lido por WebFetch); `monitor/latest` redireciona para 10.8; iso.org e vultr.com devolvem 403 à máquina
(não citados como evidência); `www.in.gov.br` tem `robots.txt` com `Disallow: /` (gate da casa; a Resolução CD/ANPD
15/2024 é citada pela página da ANPD, não pelo DOU).
