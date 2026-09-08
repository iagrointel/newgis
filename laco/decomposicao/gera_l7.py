#!/usr/bin/env python3
"""Gera /home/dev/plataforma/laco/decomposicao/L7.json (linha L7 operação e produção)."""
import json
import re
import sys

ACESSO = "2026-09-05"
LINHA = "L7 operação"

# ---------------------------------------------------------------- fontes (todas testadas por HTTP em 05/09/2026)
FONTES = [
    # Esri 11.4 (série versionada enterprise.arcgis.com; "latest" redireciona para 12.1 no doc.esri.com)
    ("E11-webgisdr", "https://enterprise.arcgis.com/en/portal/11.4/administer/linux/create-web-gis-backup.htm", 200,
     "WebGISDR export/import; BACKUP_RESTORE_MODE full|incremental; incremental exige PITR no relational data store; cache de tiles copiado à mão"),
    ("E11-dr", "https://enterprise.arcgis.com/en/portal/11.4/administer/linux/configure-disaster-recovery.htm", 200,
     "standby desconectado alimentado por export/import do webgisdr; mesma URL; sem licença extra para o standby"),
    ("E11-ha", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/high-availability-in-arcgis-enterprise.htm", 200,
     "HA = 2 cópias ativas + balanceador de terceiros com failover automático; 'human component': nunca aplicar patch nos dois ao mesmo tempo; admin sempre disponível"),
    ("E11-ha-patch", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/apply-patches-and-updates-to-highly-available-components.htm", 200,
     "patch no standby primeiro, conferir com machine Status API, depois no primário; uma máquina por vez por camada"),
    ("E11-perda-x-parada", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/choose-data-loss-downtime-prevention-method.htm", 200,
     "tabela 'downtime aceitável × perda aceitável × recursos': backup diário = ~1 dia de parada e ~1 dia de perda; réplica/HA para menos"),
    ("E11-backup-bp", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/backup-and-restore-best-practices.htm", 200,
     "alinhar agenda de backup entre componentes; código de saída do webgisdr como sinal; restore drill em cadência semirregular; geodatabase incremental a cada 15 min para RPO baixo"),
    ("E11-ha-1maq", "https://enterprise.arcgis.com/en/server/11.4/install/windows/single-machine-high-availability-active-passive-deployment.htm", 200,
     "ativo-passivo = dois sites independentes atrás de balanceador; failover quando o primário some"),
    ("E11-upgrade-portal", "https://enterprise.arcgis.com/en/portal/11.4/administer/linux/upgrade-portal-for-arcgis.htm", 200, "atualização de versão do Portal"),
    ("E11-upgrade-server", "https://enterprise.arcgis.com/en/server/11.4/install/linux/upgrade-arcgis-server.htm", 200, "atualização de versão do Server"),
    ("E11-patch", "https://enterprise.arcgis.com/en/server/11.4/install/windows/check-for-software-patches-and-updates.htm", 200,
     "utilitário patchnotification lê https://downloads.esri.com/patch_notification/patches.json, lista instalados, baixa e instala"),
    ("E11-portal-logs", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/about-portal-logs.htm", 200,
     "níveis Severe/Warning/Info/Fine/Verbose/Debug; padrão Warning após instalar; campos: nível, hora, componente, máquina, usuário, código, PID"),
    ("E11-server-logs", "https://enterprise.arcgis.com/en/server/11.4/administer/windows/about-server-logs.htm", 200, "logs do Server, apagar logs no site inteiro"),
    ("E11-audit", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/understand-audit-logs.htm", 200,
     "audit logs do Portal para SIEM; retenção herdada dos portal logs; local configurável no Portal Admin"),
    ("E11-usage", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/about-usage-reports.htm", 200,
     "Activity Dashboard embutido; relatórios por item/membro/grupo; papel personalizado com 3 privilégios mínimos"),
    ("E11-stats", "https://enterprise.arcgis.com/en/server/11.4/administer/windows/about-server-statistics.htm", 200,
     "estatísticas de serviço: contagem de pedidos, instâncias máximas, tempo máximo de resposta; relatórios no Manager"),
    ("E11-sec-bp", "https://enterprise.arcgis.com/en/server/11.4/administer/windows/best-practices-for-configuring-a-secure-environment.htm", 200,
     "HTTPS com CA; permissões de arquivo; shared key do token (AES); token em cabeçalho X-Esri-Authorization e não em query; standardized queries; desligar Services Directory"),
    ("E11-scan", "https://enterprise.arcgis.com/en/server/11.4/administer/windows/scan-arcgis-server-for-security-best-practices.htm", 200,
     "serverScan.py -n -u -p -o gera relatório HTML serverScanReport_[host]_[data].html"),
    ("E11-sec", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/configure-security.htm", 200, "segurança do Portal 11.4 (MFA por membro, sem 'Enforce')"),
    ("E11-webhooks", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/create-webhooks.htm", 200,
     "webhooks de organização (items/users/groups/roles) e de serviço (FeaturesCreated/Updated/Deleted/Posted…); receptor só HTTPS; alvo URL ou Notebook"),
    ("E11-webhook-payload", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/webhook-payloads.htm", 200,
     "payload: when, operation, source, id, userId, username, properties; 'when' de entrega e 'when' do evento"),
    ("E11-disconnected", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/configure-a-disconnected-deployment.htm", 200,
     "sem internet: CA própria confiável, desligar links sociais e conteúdo externo (esri_*), basemaps próprios em grupo"),
    ("E11-manager-lang", "https://enterprise.arcgis.com/en/server/11.4/install/windows/configuring-the-display-language-for-arcgis-server-manager.htm", 200,
     "Manager pré-localizado em 10 idiomas incl. português do Brasil e espanhol; escolhe pelo idioma do navegador"),
    ("E11-manutencao", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/best-practices-maintenance.htm", 200,
     "manutenção: membros em lote por CSV, métricas de uso na página Status"),
    ("E11-monitor", "https://enterprise.arcgis.com/en/monitor/latest/get-started/what-is-arcgis-monitor.htm", 200,
     "ArcGIS Monitor: métricas de status, disponibilidade, uso, desempenho; alertas por limiar; relatórios; produto separado (Administrator + Server)"),
    ("E11-datastore-backup", "https://enterprise.arcgis.com/en/data-store/latest/administer/linux/create-and-restore-backups.htm", 200,
     "backup/restore do ArcGIS Data Store (relational, tile cache)"),
    ("E11-general", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/configure-general.htm", 200, "configurações gerais da organização (idioma padrão, região)"),
    ("E11-token-exp", "https://enterprise.arcgis.com/en/portal/11.4/administer/windows/specify-the-default-token-expiration-time.htm", 200, "expiração de token"),
    # REST Administrator API (developers.arcgis.com, renderizado por JS; lido por WebFetch)
    ("REST-server-overview", "https://developers.arcgis.com/rest/enterprise-administration/server/overview/", 200, "ArcGIS Server Administrator API"),
    ("REST-server-logs", "https://developers.arcgis.com/rest/enterprise-administration/server/logs/", 200, "logs: query, settings, clean, count error reports"),
    ("REST-server-editlog", "https://developers.arcgis.com/rest/enterprise-administration/server/editlogsettings/", 200,
     "logLevel OFF|SEVERE|WARNING|INFO|FINE|VERBOSE|DEBUG (padrão WARNING); logDir; maxLogFileAge padrão 90 dias; maxErrorReportsCount padrão 10"),
    ("REST-server-usage", "https://developers.arcgis.com/rest/enterprise-administration/server/usagereports/", 200, "usagereports: criar relatório, métrica RequestCount, since=LAST_MONTH"),
    ("REST-server-usage-settings", "https://developers.arcgis.com/rest/enterprise-administration/server/usagereportssettings/", 200,
     "samplingInterval em minutos (exemplo 30) em memória antes de gravar; maxHistory em dias, 0 = para sempre"),
    ("REST-server-secconfig", "https://developers.arcgis.com/rest/enterprise-administration/server/securityconfig/", 200,
     "sslEnabled, httpEnabled, HSTSEnabled, httpsProtocols, cipherSuites, allowDirectAccess (6080), virtualDirsSecurityEnabled, allowedAdminAccessIPs, authenticationMode ARCGIS_TOKEN, contentSecurityPolicy padrão \"script-src 'self';\""),
    ("REST-server-props", "https://developers.arcgis.com/rest/enterprise-administration/server/serverproperties/", 200,
     "uploadFileExtensionAllowedList (soe,sd,sde,odc,csv,txt,zshp,kmz,geodatabase); maxHttpPostSizeInBytes 10 MB; diskSpaceThresholdGB 5; enableNosniffHeader; featureServiceXSSFilter=input; standardizedQueries=true; webServerMaxRequestThreads 150; readOnlyMode*; disableIPLogging; httpProxy*"),
    ("REST-server-mode", "https://developers.arcgis.com/rest/enterprise-administration/server/mode/", 200,
     "site mode EDITABLE|READ_ONLY: READ_ONLY bloqueia publicação e a maioria das operações admin, reinicia serviços e copia configuração para repositório local"),
    ("REST-server-status", "https://developers.arcgis.com/rest/enterprise-administration/server/status/", 200,
     "machines/<m>/status: configuredState × realTimeState (STARTED/STOPPED); usar o real"),
    ("REST-server-webhooks", "https://developers.arcgis.com/rest/enterprise-administration/server/webhooks/", 200,
     "webhooks de feature service e geoprocessing no Server Admin; organização no Portal; entrega por HTTPS POST"),
    ("REST-server-webhook-settings", "https://developers.arcgis.com/rest/enterprise-administration/server/webhook-settings/", 200,
     "notificationAttempts 1-5; notificationTimeOutInSeconds; notificationElapsedTimeInSeconds (padrão 5 s entre tentativas); política de desativação por falhas em janela de dias"),
    ("REST-server-system", "https://developers.arcgis.com/rest/enterprise-administration/server/system/", 200, "system: licenses, configstore, directories, handlers, jobs, platformservices, properties, webadaptors, deployment"),
    ("REST-server-security", "https://developers.arcgis.com/rest/enterprise-administration/server/security/", 200, "security: users, roles, tokens, config, PSA"),
    ("REST-server-machines", "https://developers.arcgis.com/rest/enterprise-administration/server/machines/", 200, "máquinas do site"),
    ("REST-portal", "https://developers.arcgis.com/rest/enterprise-administration/portal/", 200, "Portal Administrator API"),
    ("REST-portal-system", "https://developers.arcgis.com/rest/enterprise-administration/portal/system/", 200,
     "system: webadaptors, directories, database, indexer, properties, emailsettings, languages, content, mode, licenses, federation"),
    ("REST-portal-sysprops", "https://developers.arcgis.com/rest/enterprise-administration/portal/system-properties/", 200,
     "privatePortalURL, WebContextURL, disableSignup, enableNosniffHeader, httpProxy*, nonProxyHosts, ldapCertificateValidation, diskSpaceThresholdGB 5, logBackupWarning (11.1+), useROConnectionForQueries (11.4+)"),
    ("REST-portal-email", "https://developers.arcgis.com/rest/enterprise-administration/portal/email-settings/", 200,
     "smtpHost, smtpPort, mailFrom, mailFromLabel, encryptionMethod SSL|TLS|NONE, authRequired, smtpUser, smtpPass; operações update/test/delete"),
    ("REST-portal-languages", "https://developers.arcgis.com/rest/enterprise-administration/portal/languages/", 200,
     "42 códigos esri_* (incl. esri_pt, esri_es); recurso deprecado desde 11.2, substituído por conteúdo por idioma"),
    ("REST-portal-mode", "https://developers.arcgis.com/rest/enterprise-administration/portal/mode/", 200,
     "modo somente leitura: portal + servidores federados + data stores; bloqueia POST e admin; leitura continua"),
    ("REST-portal-export", "https://developers.arcgis.com/rest/enterprise-administration/portal/export-site/", 200,
     "exportSite gera .portalsite com content directory + banco; snapshot pode não refletir mudança concorrente; 12.0 aceita prefixo em nuvem"),
    ("REST-portal-import", "https://developers.arcgis.com/rest/enterprise-administration/portal/import-site/", 200, "importSite"),
    ("REST-portal-logs", "https://developers.arcgis.com/rest/enterprise-administration/portal/logs/", 200, "logs do Portal por REST"),
    ("REST-portal-security", "https://developers.arcgis.com/rest/enterprise-administration/portal/security/", 200, "segurança do Portal por REST"),
    ("REST-portal-secupdate", "https://developers.arcgis.com/rest/enterprise-administration/portal/update-security-configuration/", 200, "allowedProxyHosts, allowedOrigins, disableServicesDirectory etc."),
    ("REST-portal-licenses", "https://developers.arcgis.com/rest/enterprise-administration/portal/licenses/", 200, "licenças por REST (modelo para licença do appliance)"),
    ("REST-org-webhooks", "https://developers.arcgis.com/rest/users-groups-and-items/webhooks/", 200, "webhooks de organização: lista ativados e desativados"),
    ("REST-featureservice", "https://developers.arcgis.com/rest/services-reference/enterprise/feature-service/", 200, "FeatureServer (where, outFields, orderBy…) — alvo do teste de injeção"),
    ("REST-applyedits", "https://developers.arcgis.com/rest/services-reference/enterprise/apply-edits-feature-service-layer/", 200, "applyEdits — cenário de carga de edição"),
    ("DEV-python", "https://developers.arcgis.com/python/latest/", 200, "ArcGIS API for Python (paridade do SDK)"),
    ("DEV-js", "https://developers.arcgis.com/javascript/latest/", 200, "ArcGIS Maps SDK for JavaScript (paridade do SDK JS)"),
    ("DEV-apikey", "https://developers.arcgis.com/documentation/security-and-authentication/api-key-authentication/", 200, "chaves de API com escopo e expiração"),
    ("ESRI-patches", "https://support.esri.com/en-us/patches-updates", 200, "página de patches e atualizações"),
    ("ESRI-trust", "https://trust.arcgis.com/en/", 200, "ArcGIS Trust Center (modelo de 'postura de segurança escrita')"),
    ("ESRI-vpat", "https://www.esri.com/en-us/legal/accessibility/conformance-reports", 200,
     "ACR/VPAT publicados: ArcGIS Enterprise 12.1 (2026), 12.0, 11.5, 11.3, 11.1, 10.9.1; Map Viewer jun/2025; Experience Builder fev/2026; Dashboards jun/2025; Instant Apps out/2023; Survey123 2026; Field Maps set/2021"),
    # GeoServer / QGIS Server
    ("GS-production", "https://docs.geoserver.org/stable/en/user/production/index.html", 200, "checklist de produção: Java, contêiner, configuração, dado, init scripts"),
    ("GS-controlflow", "https://docs.geoserver.org/stable/en/user/extensions/controlflow/index.html", 200,
     "control-flow: ows.global=<n>, por usuário (cookie) ou por IP, fila com timeout; limita memória por concorrência"),
    ("GS-monitoring", "https://docs.geoserver.org/stable/en/user/extensions/monitoring/index.html", 200, "monitor extension: pedidos persistidos em banco, audit log, query API, GeoIP"),
    ("GS-backup", "https://docs.geoserver.org/stable/en/user/community/backuprestore/index.html", 200, "backup/restore do catálogo (workspaces, stores, layers, styles, GWC) em arquivo portátil, por REST e UI, com filtro"),
    ("GS-security", "https://docs.geoserver.org/stable/en/user/security/index.html", 200, "roles, auth, senhas, service/layer security, filesystem sandboxing, REST security, URL checks, CSP"),
    ("GS-rest", "https://docs.geoserver.org/stable/en/user/rest/index.html", 200, "REST de administração"),
    ("GS-advisories", "https://github.com/geoserver/geoserver/security/advisories", 200, "advisories de segurança publicados no GitHub"),
    ("QGIS-server", "https://docs.qgis.org/3.40/en/docs/server_manual/index.html", 200, "manual do QGIS Server 3.40"),
    ("QGIS-server-config", "https://docs.qgis.org/3.40/en/docs/server_manual/config.html", 200,
     "QGIS_SERVER_LOG_LEVEL 0|1|2, LOG_STDERR, LOG_PROFILE, MAX_THREADS, CACHE_DIRECTORY/SIZE, ALLOWED_EXTRA_SQL_TOKENS, OVERRIDE_SYSTEM_LOCALE, LANDING_PAGE_*"),
    # Pilha aberta
    ("PGBR-guide", "https://pgbackrest.org/user-guide.html", 200, "full/diff/incr; retenção repo1-retention-full; repo S3-compatível; PITR; delta restore; block incremental; backup-standby"),
    ("PGBR-config", "https://pgbackrest.org/configuration.html", 200, "referência de configuração"),
    ("PGBR-command", "https://pgbackrest.org/command.html", 200, "comandos backup/restore/expire/verify/check"),
    ("PG-standby", "https://www.postgresql.org/docs/16/warm-standby.html", 200, "streaming replication, hot standby, synchronous, promote"),
    ("PG-archiving", "https://www.postgresql.org/docs/16/continuous-archiving.html", 200, "archive_mode/archive_command e PITR"),
    ("PG-ha", "https://www.postgresql.org/docs/16/high-availability.html", 200, "alta disponibilidade"),
    ("PG-rls", "https://www.postgresql.org/docs/16/ddl-rowsecurity.html", 200, "row level security"),
    ("PG-pgstat", "https://www.postgresql.org/docs/16/pgstatstatements.html", 200, "pg_stat_statements"),
    ("PG-logging", "https://www.postgresql.org/docs/16/runtime-config-logging.html", 200, "log_min_duration_statement etc."),
    ("PGAUDIT", "https://www.pgaudit.org/", 200, "auditoria de sessão/objeto via log do Postgres (já em shared_preload_libraries desta máquina)"),
    ("PGBOUNCER", "https://www.pgbouncer.org/config.html", 200, "pool transaction/session"),
    ("PATRONI", "https://patroni.readthedocs.io/en/latest/", 200, "failover automático de Postgres (avaliado, não recomendado para 2 nós sem DCS)"),
    ("GARAGE-admin", "https://garagehq.deuxfleurs.fr/documentation/reference-manual/admin-api/", 200,
     "admin API v2 (Garage 2.0): bearer token; tokens com escopo; metrics_token separado; /metrics"),
    ("GARAGE-mon", "https://garagehq.deuxfleurs.fr/documentation/cookbook/monitoring/", 200, "Prometheus em [admin] api_bind_addr :3903/metrics; metrics_token"),
    ("GARAGE-upgrade", "https://garagehq.deuxfleurs.fr/documentation/operations/upgrading/", 200, "minor sem parada; major só entre versões contíguas, com guia; snapshot antes"),
    ("GARAGE-layout", "https://garagehq.deuxfleurs.fr/documentation/operations/layout/", 200, "layout de nós e zonas"),
    ("GARAGE-durability", "https://garagehq.deuxfleurs.fr/documentation/operations/durability-repairs/", 200, "scrub/repair"),
    ("GARAGE-features", "https://garagehq.deuxfleurs.fr/documentation/reference-manual/features/", 200, "replication_factor 1/2/3, cotas por bucket, versionamento"),
    ("GARAGE-s3", "https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/", 200, "compatibilidade S3 (pgBackRest repo-type=s3)"),
    ("PROM-alert", "https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/", 200, "regras de alerta"),
    ("PROM-am", "https://prometheus.io/docs/alerting/latest/alertmanager/", 200, "Alertmanager (apt 0.26.0)"),
    ("PROM-node", "https://github.com/prometheus/node_exporter", 200, "node_exporter (já roda aqui em 127.0.0.1:9100)"),
    ("PROM-pg", "https://github.com/prometheus-community/postgres_exporter", 200, "postgres_exporter (apt 0.15.0)"),
    ("PROM-nginx", "https://github.com/nginx/nginx-prometheus-exporter", 200, "nginx exporter (apt 1.1.0)"),
    ("PROM-blackbox", "https://github.com/prometheus/blackbox_exporter", 200, "sondas HTTP/TLS (validade de certificado)"),
    ("PROM-client", "https://prometheus.github.io/client_python/", 200, "prometheus_client (a API da casa em :8002 já expõe /metrics com ele)"),
    ("GRAFANA-prov", "https://grafana.com/docs/grafana/latest/administration/provisioning/", 200, "painéis e fontes por arquivo"),
    ("GRAFANA-alert", "https://grafana.com/docs/grafana/latest/alerting/", 200, "alerting do Grafana (alternativa ao Alertmanager)"),
    ("LOKI", "https://grafana.com/docs/loki/latest/", 200, "logs consultáveis por rótulo/req_id"),
    ("OTEL-py", "https://opentelemetry.io/docs/languages/python/", 200, "rastreamento distribuído (fase 2)"),
    ("K6", "https://grafana.com/docs/k6/latest/", 200, "k6 (não está no apt do Ubuntu; binário GitHub ou repositório da Grafana)"),
    ("K6-thresholds", "https://grafana.com/docs/k6/latest/using-k6/thresholds/", 200, "thresholds: http_req_failed rate<0.01, http_req_duration p(95)<200; exit code ≠ 0"),
    ("K6-scenarios", "https://grafana.com/docs/k6/latest/using-k6/scenarios/", 200, "cenários com executores (ramping-vus, constant-arrival-rate)"),
    ("NGINX-slice", "https://nginx.org/en/docs/http/ngx_http_slice_module.html", 200, "slice para cache de range (já usado na prova do pipeline)"),
    ("NGINX-limit", "https://nginx.org/en/docs/http/ngx_http_limit_req_module.html", 200, "limit_req (zonas perip/authip já existem no nginx da casa)"),
    ("NGINX-proxy", "https://nginx.org/en/docs/http/ngx_http_proxy_module.html", 200, "proxy_cache, proxy_cache_lock, use_stale"),
    ("CF-default", "https://developers.cloudflare.com/cache/concepts/default-cache-behavior/", 200, "o que a Cloudflare cacheia por padrão (extensão)"),
    ("CF-rules", "https://developers.cloudflare.com/cache/how-to/cache-rules/", 200, "Cache Rules: Free 10, Pro 25, Business 50, Enterprise 300"),
    ("CF-cc", "https://developers.cloudflare.com/cache/concepts/cache-control/", 200, "Cache-Control na borda"),
    ("CF-purge-prefix", "https://developers.cloudflare.com/cache/how-to/purge-cache/purge_by_prefix/", 200, "purge por prefixo, 100 prefixos por pedido; usar URL pós-transformação"),
    ("CF-purge", "https://developers.cloudflare.com/cache/how-to/purge-cache/", 200, "purge"),
    ("CF-regional", "https://developers.cloudflare.com/data-localization/regional-services/", 200,
     "Regional Services: terminação TLS e cache só na região configurada (produto do Data Localization Suite; plano Enterprise)"),
    ("CF-dls", "https://developers.cloudflare.com/data-localization/", 200, "Data Localization Suite"),
    ("CF-r2", "https://developers.cloudflare.com/r2/", 200, "R2 (location hint SA, sem garantia de residência)"),
    ("CF-workers", "https://developers.cloudflare.com/workers/", 200, "Workers (validação de token na borda, opcional)"),
    ("BUNNY-docs", "https://docs.bunny.net/docs", 200, "Bunny CDN (PoPs no Brasil; alternativa quando o ToS da Cloudflare pesar)"),
    ("BUNNY-net", "https://bunny.net/network/", 200, "rede Bunny"),
    ("B2-pricing", "https://www.backblaze.com/cloud-storage/pricing", 200, "B2 US$ 6,95/TB-mês; sem região na América do Sul"),
    ("B2-regions", "https://www.backblaze.com/docs/cloud-storage-data-regions", 200, "regiões B2: US West/East, EU Central, CA East"),
    ("HETZNER-cert", "https://www.hetzner.com/unternehmen/zertifizierung/", 200, "certificação ISO 27001 cobre todos os serviços de hospedagem e data centers da Hetzner Online GmbH"),
    ("VULTR-docs", "https://docs.vultr.com/", 200, "documentação Vultr (este servidor iagrosat-db-sp é Vultr São Paulo)"),
    ("DOCKER-compose", "https://docs.docker.com/compose/", 200, "docker compose (docker 29.1.3 instalado aqui)"),
    ("DOCKER-compose-file", "https://docs.docker.com/compose/compose-file/", 200, "referência do compose file (profiles, healthcheck, secrets)"),
    ("UBUNTU-lts", "https://ubuntu.com/about/release-cycle", 200, "ciclo de vida 24.04 LTS"),
    ("SYSTEMD-creds", "https://man7.org/linux/man-pages/man1/systemd-creds.1.html", 200, "systemd-creds / LoadCredential para segredo fora do .env"),
    ("SYSTEMD-exec", "https://man7.org/linux/man-pages/man5/systemd.exec.5.html", 200, "LoadCredential=, ProtectSystem=, etc."),
    ("SYSTEMD-timer", "https://man7.org/linux/man-pages/man5/systemd.timer.5.html", 200, "timers (padrão da casa: os timers de backup dos SIGs de teste)"),
    ("CERTBOT", "https://certbot.eff.org/", 200, "certbot (timer ativo nesta máquina)"),
    ("LE-limits", "https://letsencrypt.org/docs/rate-limits/", 200, "limites do Let's Encrypt (renovações por domínio)"),
    ("SIGSTORE", "https://sigstore.dev/", 200, "cosign (assinatura de artefato)"),
    ("COSIGN", "https://github.com/sigstore/cosign", 200, "cosign"),
    ("AGE", "https://github.com/FiloSottile/age", 200, "age (cifra de arquivo)"),
    ("SOPS", "https://github.com/getsops/sops", 200, "sops (segredos versionados cifrados)"),
    ("OPENBAO", "https://openbao.org/", 200, "OpenBao (cofre; avaliado, fora do escopo inicial)"),
    ("PIP-AUDIT", "https://github.com/pypa/pip-audit", 200, "pip-audit"),
    ("OSV", "https://github.com/google/osv-scanner", 200, "osv-scanner (Python + npm + lockfiles)"),
    ("TRIVY", "https://github.com/aquasecurity/trivy", 200, "trivy (imagem/FS; não está no apt)"),
    ("GITLEAKS", "https://github.com/gitleaks/gitleaks", 200, "gitleaks"),
    ("BANDIT", "https://bandit.readthedocs.io/en/latest/", 200, "bandit (SAST Python)"),
    ("SEMGREP", "https://semgrep.dev/docs/", 200, "semgrep"),
    ("ZAP", "https://www.zaproxy.org/docs/", 200, "OWASP ZAP baseline scan"),
    ("CLAMAV", "https://docs.clamav.net/manual/Installing.html", 200, "ClamAV (apt 1.5.3; clamd + clamdscan)"),
    ("CLAMAV-scan", "https://docs.clamav.net/manual/Usage/Scanning.html", 200, "varredura"),
    ("ASVS", "https://owasp.org/www-project-application-security-verification-standard/", 200, "OWASP ASVS"),
    ("ASVS-rel", "https://github.com/OWASP/ASVS/releases", 200, "última estável v5.0.0 (30/05/2025); 4.0.3 anterior"),
    ("WSTG", "https://owasp.org/www-project-web-security-testing-guide/", 200, "guia de teste (checklist de pentest)"),
    ("OWASP-CSP", "https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html", 200, "CSP"),
    ("OWASP-SSRF", "https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html", 200, "SSRF"),
    ("OWASP-UPLOAD", "https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html", 200, "upload"),
    ("MDN-CSP", "https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP", 200, "CSP"),
    ("MDN-HSTS", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security", 200, "HSTS"),
    ("MDN-PP", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Permissions-Policy", 200, "Permissions-Policy"),
    ("MDN-COOP", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cross-Origin-Opener-Policy", 200, "COOP"),
    ("MDN-CORP", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cross-Origin-Resource-Policy", 200, "CORP"),
    ("MDN-CORS", "https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS", 200, "CORS"),
    ("MOZ-OBS", "https://developer.mozilla.org/en-US/observatory", 200, "HTTP Observatory (nota de cabeçalhos)"),
    ("MOZ-TLS", "https://ssl-config.mozilla.org/", 200, "gerador de configuração TLS (perfil intermediate)"),
    ("SSLLABS", "https://www.ssllabs.com/ssltest/", 200, "teste TLS externo"),
    ("RFC9421", "https://www.rfc-editor.org/rfc/rfc9421", 200, "HTTP Message Signatures"),
    ("RFC9457", "https://www.rfc-editor.org/rfc/rfc9457", 200, "Problem Details (formato de erro da API)"),
    ("RFC6585", "https://www.rfc-editor.org/rfc/rfc6585", 200, "429 Too Many Requests"),
    ("RFC9110", "https://www.rfc-editor.org/rfc/rfc9110", 200, "HTTP semantics (Retry-After, 503)"),
    ("RFC9111", "https://www.rfc-editor.org/rfc/rfc9111", 200, "HTTP caching"),
    ("RFC9116", "https://www.rfc-editor.org/rfc/rfc9116", 200, "security.txt"),
    ("RFC8555", "https://www.rfc-editor.org/rfc/rfc8555", 200, "ACME"),
    ("STDWEBHOOKS", "https://www.standardwebhooks.com/", 200, "Standard Webhooks: webhook-id, webhook-timestamp, webhook-signature (HMAC-SHA256), proteção a replay"),
    ("STDWEBHOOKS-gh", "https://github.com/standard-webhooks/standard-webhooks", 200, "especificação"),
    ("STRIPE-wh", "https://docs.stripe.com/webhooks", 200, "referência de mercado para assinatura e retentativa"),
    ("OAS31", "https://spec.openapis.org/oas/v3.1.0", 200, "OpenAPI 3.1"),
    ("FASTAPI-wh", "https://fastapi.tiangolo.com/advanced/openapi-webhooks/", 200, "webhooks no OpenAPI do FastAPI"),
    ("OPENAPI-PY", "https://github.com/openapi-generators/openapi-python-client", 200, "gerador de cliente Python"),
    ("OPENAPI-GEN", "https://openapi-generator.tech/", 200, "gerador multi-linguagem (JS/TS)"),
    ("REDOC", "https://github.com/Redocly/redoc", 200, "portal de API vendorizável"),
    ("SCALAR", "https://github.com/scalar/scalar", 200, "portal de API com 'experimente' (vendorizável)"),
    ("SEMVER", "https://semver.org/lang/pt-BR/", 200, "semver 2.0.0"),
    ("CHANGELOG", "https://keepachangelog.com/pt-BR/1.1.0/", 200, "keep a changelog 1.1.0"),
    ("WCAG21", "https://www.w3.org/TR/WCAG21/", 200, "WCAG 2.1"),
    ("WCAG22", "https://www.w3.org/TR/WCAG22/", 200, "WCAG 2.2 (recomendação vigente do W3C; superconjunto da 2.1)"),
    ("WCAG-quick", "https://www.w3.org/WAI/WCAG21/quickref/", 200, "referência rápida"),
    ("EMAG", "https://emag.governoeletronico.gov.br/", 200, "eMAG 3.1 (abril/2014), versão brasileira especializada da WCAG para governo; CC BY 4.0"),
    ("GOVBR-a11y", "https://www.gov.br/governodigital/pt-br/acessibilidade-e-usuario/acessibilidade-digital", 200, "acessibilidade digital gov.br"),
    ("AXE", "https://github.com/dequelabs/axe-core", 200, "axe-core"),
    ("AXE-PW-PY", "https://pypi.org/project/axe-playwright-python/", 200, "axe para playwright em Python (pytest já é o padrão do repo)"),
    ("PW-PY", "https://playwright.dev/python/docs/intro", 200, "playwright python (chromium do playwright; google-chrome headless quebra nesta máquina)"),
    ("FLUENT", "https://projectfluent.org/", 200, "Fluent (formato de mensagem; alternativa ao ICU)"),
    ("BABEL", "https://babel.pocoo.org/en/latest/", 200, "Babel 2.10.3 já no Python do sistema (plural, número, data por locale)"),
    ("I18NEXT", "https://www.i18next.com/", 200, "i18next (front; avaliado)"),
    ("LGPD", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm", 200,
     "Lei 13.709/2018: art. 37 registro das operações; art. 46 medidas de segurança; art. 48 comunicação de incidente; art. 33 transferência internacional"),
    ("ANPD-incidente", "https://www.gov.br/anpd/pt-br/assuntos/incidente-de-seguranca", 200,
     "Resolução CD/ANPD 15/2024 (24/04/2024) = Regulamento de Comunicação de Incidentes; comunicação preliminar e completa; PAI; comunicar titulares em risco relevante; e-mail incidentes@anpd.gov.br"),
    ("ANPD-cis", "https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis", 200, "formulário CIS preliminar/completo/complementar"),
    ("ANPD-transf", "https://www.gov.br/anpd/pt-br/assuntos/transferencia-internacional-de-dados", 200, "transferência internacional (nó Europa exige cláusula)"),
    ("ANPD-guia-agentes", "https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia-orientativo-para-definicoes-dos-agentes-de-tratamento-de-dados-pessoais-e-do-encarregado", 200, "controlador × operador × encarregado (DPA)"),
    ("GOVBR-privsec", "https://www.gov.br/governodigital/pt-br/privacidade-e-seguranca", 200, "privacidade e segurança gov.br"),
    ("INDE", "https://inde.gov.br/", 200, "INDE"),
    ("INDE-meta", "https://metadados.inde.gov.br/", 200, "catálogo de metadados INDE (publicação CSW; fica em L0-09)"),
    ("UPTIME-KUMA", "https://github.com/louislam/uptime-kuma", 200, "status page pronta (avaliada)"),
    ("GATUS", "https://github.com/TwiN/gatus", 200, "status page declarativa (avaliada)"),
    ("UPPTIME", "https://github.com/upptime/upptime", 200, "status page estática (avaliada)"),
    ("PROC", "https://procrastinate.readthedocs.io/en/stable/", 200, "Procrastinate (fila L0-05; métricas de fila)"),
    ("TIPG", "https://github.com/developmentseed/tipg", 200, "tipg (OGC API Features)"),
    ("TITILER", "https://developmentseed.org/titiler/", 200, "TiTiler (expõe /metrics? conferir no item)"),
    ("MARTIN", "https://maplibre.org/martin/", 200, "Martin (métricas Prometheus nativas)"),
    ("PGSTAC", "https://stac-utils.github.io/pgstac/", 200, "pgstac"),
    ("PG-versioning", "https://www.postgresql.org/support/versioning/", 200, "política de versões do PostgreSQL (16 até nov/2028)"),
    ("PG-upgrade", "https://www.postgresql.org/docs/16/pgupgrade.html", 200, "pg_upgrade (atualização maior do banco no appliance)"),
    ("RCLONE", "https://rclone.org/docs/", 200, "rclone (cópia Garage → B2)"),
    ("RESTIC", "https://restic.readthedocs.io/en/stable/", 200, "restic (backup de arquivos com deduplicação; avaliado)"),
]

# ---------------------------------------------------------------- itens
ITENS = []


def it(id_, prio, hip, portao, ref, papeis, tam, deps, origem, pai=None, bloqueio=None, fontes=(), notas=None):
    d = {
        "id": id_, "linha": LINHA, "prioridade": prio, "estado": "pendente", "dependencias": deps,
        "hipotese": hip, "portao_de_pronto": portao, "refutacao": ref, "papeis": papeis, "tamanho": tam,
        "tentativas": 0, "turno": None, "bloqueio": bloqueio, "pai": pai, "origem": origem, "fontes": list(fontes),
    }
    if notas:
        d["notas"] = notas
    ITENS.append(d)


# ===== 1. Instalação, pacote, atualização, release ===================================================
it("L7-01-a-compose-perfis", 2,
   "o mesmo repositório produz DUAS formas de instalação a partir dos MESMOS arquivos: `install.sh` (hospedado, systemd, já existe e é medido em 6-9 s) e `docker compose` com perfis `hospedado` e `appliance` (Postgres 16+PostGIS 3.6+pgRouting+pgstac, Garage, Martin, TiTiler, API, worker, nginx). Um Dockerfile por serviço, imagens construídas do repositório, sem imagem de terceiro além das bases oficiais; migrações e semeadura idênticas nos dois caminhos",
   "`docker compose --profile appliance up -d` em máquina com só docker sobe todos os serviços com healthcheck verde em ≤ 10 min (medido); `curl /saude` = 200 com `migracoes_pendentes 0`; a MESMA suíte `make check` roda contra o compose e contra o systemd e passa nos dois; diff entre o esquema do banco criado pelos dois caminhos = vazio (`pg_dump -s` comparado); imagens sem `latest`, cada uma com digest fixado em `deploy/compose/VERSOES.txt`",
   "adversário sobe o compose em máquina sem nenhum pacote da casa e sem acesso ao `~/.local` (quebra já vista pelo adversário T1) e roda `make check`; qualquer serviço sem healthcheck, qualquer `latest`, ou diferença de esquema entre os dois caminhos = refutado",
   ["arquiteto", "backend", "testador", "adversario"], "M", ["L0-01-repo", "L1-01-ingest-raster", "L2-01-mapa-web"], "casa", pai="L7-01-instalador-limpo",
   fontes=["DOCKER-compose", "DOCKER-compose-file", "GS-production", "QGIS-server-config"])

it("L7-01-b-instalacao-conteiner-limpo", 2,
   "prova de instalação do zero: contêiner Ubuntu 24.04 limpo (docker) recebe só o repositório e roda `install.sh`; corrige as duas quebras do adversário T1 (dependências vindas de `~/.local` em vez de `requirements.txt`; senha de demonstração passada em argv de sudo e gravada no journal) e a atomicidade do nginx (`nginx -t` ANTES do `mv` para sites-enabled)",
   "`tests/instalacao/limpo.sh` cria o contêiner, copia o repositório, roda `install.sh` e `make check`; sai 0; `journalctl` do contêiner sem nenhuma senha (grep das senhas geradas = 0 linhas); `PYTHONNOUSERSITE=1 venv/bin/python -c 'import app.main'` funciona; tempo total registrado em `tests/medidas/L7-01-b.json`; documento `docs/INSTALACAO.md` com cada pré-requisito listado e conferido pelo próprio script (`install.sh` para com mensagem nomeando o que falta)",
   "adversário segue só `docs/INSTALACAO.md` num contêiner e anota cada passo que falhou ou exigiu conhecimento não escrito; um passo = refutado",
   ["backend", "testador", "adversario"], "M", ["L7-01-a-compose-perfis"], "casa", pai="L7-01-instalador-limpo", fontes=["UBUNTU-lts", "PW-PY"])

it("L7-01-c-dado-demonstracao", 3,
   "pacote de dado de demonstração 100 % aberto e pequeno (≤ 300 MB no repositório ou baixado do bucket da casa por sha256): 1 cena Sentinel-2 recortada, 1 ortofoto aberta, camadas vetoriais abertas (limites IBGE, OSM de um município, BDGD de um alimentador), 1 mapa, 1 painel, 1 formulário, 1 rede; semeado por `install.sh --demo` e pelo compose; é o dado que o manual, o tour, o roteiro de demonstração e o teste de carga usam",
   "`plat demo semear` cria o inquilino `demo` com os itens listados e `plat demo verificar` confere contagens e sha256; nenhum arquivo com nome de cliente/parceiro/piloto (grep = 0); licença de cada dado escrita em `dados/demo/LICENCAS.md` com URL; tamanho medido ≤ 300 MB; semeadura idempotente (rodar 2× = mesmo estado)",
   "adversário procura no pacote qualquer dado não aberto, qualquer nome de cliente, qualquer arquivo sem licença declarada, ou semeadura que duplica ao repetir",
   ["dados", "raster", "cronista", "adversario"], "P", ["L0-04-ingest-vetor", "L1-01-ingest-raster"], "casa", pai="L7-01-instalador-limpo")

it("L7-35-atualizacao-versao-assinada", 2,
   "atualização de versão em um comando (`plat atualizar vX.Y.Z`): baixa o pacote (tar) + manifesto sha256 + assinatura ed25519; recusa pacote não assinado; entra em modo somente-leitura (L7-33); faz backup lógico do schema `plat` antes; aplica migrações (imutáveis, só para frente, padrão expandir/contrair); reinicia serviços um a um; sai do modo somente-leitura; grava linha em `plat.versao_instalada` (versão anterior, nova, sha, quando, duração, quem). Rollback = código anterior + restauração do backup lógico, documentado e testado. Modelo Esri: ordem de atualização Portal → Server → Data Store e o utilitário patchnotification",
   "teste sobe 0.1.0, atualiza para 0.2.0 sintética com migração nova, e volta: sessões ativas sobrevivem (cookie continua válido), `/saude` mostra a versão nova e `migracoes_pendentes 0`; pacote alterado em 1 byte é recusado com mensagem; tempo de indisponibilidade de escrita medido e registrado; `docs/ATUALIZACAO.md` com o procedimento e o rollback; teste automatizado do rollback",
   "adversário altera o manifesto, reassina com outra chave, e tenta atualizar; tenta atualizar com migração que falha no meio (deve ficar na versão anterior, nunca em estado intermediário); mata o processo no meio da atualização e reinicia",
   ["arquiteto", "backend", "testador", "adversario"], "M", ["L7-15-processo-release", "L7-16-assinatura-pacote", "L7-33-modo-somente-leitura", "L0-06-backup-status"], "esri",
   fontes=["E11-upgrade-portal", "E11-upgrade-server", "E11-patch", "E11-ha-patch", "GARAGE-upgrade", "SEMVER"])

it("L7-15-processo-release", 2,
   "processo de release escrito e executado por script: semver 2.0.0 em `VERSAO`; CHANGELOG no formato keep-a-changelog gerado a partir dos commits do turno; etiqueta git `vX.Y.Z` assinada; `make check` inteiro + e2e + carga curta em HOMOLOGAÇÃO (L7-31) antes de produção; hotfix = ramo `hotfix/X.Y.Z+1`; congelamento de esquema por versão menor; regra: nenhuma versão vai para produção sem ter passado por homologação com o mesmo pacote (mesmo sha)",
   "`scripts/release.sh X.Y.Z` executa tudo e para no primeiro erro; a saída registra o sha do pacote testado em homologação e o mesmo sha instalado em produção; `CHANGELOG.md` tem a seção da versão com Adicionado/Alterado/Corrigido/Segurança; três releases sintéticas feitas no teste (patch, minor, hotfix) com evidência; `docs/RELEASE.md`",
   "adversário tenta instalar em produção um pacote que não passou por homologação (o script tem de recusar) e procura no CHANGELOG uma versão sem etiqueta git ou etiqueta sem changelog",
   ["gerente", "backend", "cronista", "adversario"], "P", ["L7-31-ambiente-homologacao", "L7-16-assinatura-pacote"], "usuario", fontes=["SEMVER", "CHANGELOG"])

it("L7-16-assinatura-pacote", 2,
   "assinatura e verificação de pacote: par ed25519 da casa (chave privada fora do repositório, em credencial do systemd; pública embutida no código e no appliance); `scripts/empacotar.sh` gera `plat-X.Y.Z.tar.zst` + `MANIFESTO.sha256` + `MANIFESTO.sig`; `plat verificar-pacote` valida offline (o appliance não tem internet); cosign avaliado e descartado para o appliance porque o modo keyless exige rede",
   "assinar e verificar funcionam sem rede; alterar 1 byte de qualquer arquivo do tar = verificação falha; a chave privada nunca aparece no git (`gitleaks` = 0) nem em argv; rotação da chave documentada com período de dupla chave (pacote assinado com a nova é aceito por appliance que ainda só conhece a antiga? NÃO: por isso a pública nova é distribuída numa versão antes de ser usada; teste desse fluxo)",
   "adversário monta pacote assinado com chave própria e tenta instalar; tenta substituir a chave pública embutida via variável de ambiente ou arquivo de configuração",
   ["arquiteto", "backend", "adversario"], "P", ["L0-01-repo"], "usuario", fontes=["SIGSTORE", "COSIGN", "AGE"])

it("L7-14-extensoes-fdw", 4,
   "extensões e binários que a plataforma precisa e que exigem apt/sudo ou licença de terceiro, instalados pelo `install.sh`/compose de forma declarada e verificável: pgRouting, pgstac, pg_partman, `postgres_fdw`/`file_fdw` (já disponíveis), `tds_fdw` (SQL Server referenciado, L6-02-j) e `oracle_fdw` (exige Instant Client da Oracle: licença e download são decisão do dono — sem ela Oracle fica fora e a lista `docs/EXTENSOES.md` diz isso); no appliance, o cliente registra o próprio banco (L3L6) e as mesmas extensões têm de estar na imagem do Postgres do compose; `pg_available_extensions` medido 05/09 nesta máquina: só postgres_fdw e file_fdw dos FDW",
   "`plat extensoes verificar` lista cada extensão com versão instalada × versão exigida e sai ≠ 0 quando falta; a imagem Postgres do compose traz todas as livres (teste `CREATE EXTENSION` de cada uma num contêiner limpo); `docs/EXTENSOES.md` com licença, origem e comando por extensão; oracle_fdw marcado 'pendente de decisão do dono' até haver decisão",
   "adversário instala o compose e roda `CREATE EXTENSION` de cada uma das extensões declaradas; uma que falhe sem estar marcada como pendente = refutado",
   ["dados", "arquiteto", "adversario"], "P", ["L7-01-a-compose-perfis"], "casa", bloqueio="oracle_fdw: licença do Instant Client (decisão do dono)", fontes=["PG-versioning", "PGSTAC"])

it("L7-31-ambiente-homologacao", 2,
   "ambiente de homologação na mesma máquina: unidade `plat-homolog` na porta 8154, banco SEPARADO `plat_homolog` (CREATE DATABASE, não schema, para que migração e restore sejam idênticos aos de produção), bucket Garage `homolog-*`, subdomínio `homolog.plat.iagrointel.com` (DNS-only, noindex, protegido por senha básica no nginx), dado sintético (L7-01-c) mais uma cópia anonimizada do inquilino demo; é onde a release roda antes de produção e onde o adversário ataca sem tocar produção",
   "`install.sh --ambiente homolog` cria tudo idempotente; `make check` e e2e passam contra a URL de homologação; produção e homologação nunca compartilham banco, bucket, chave ou segredo (teste lê os dois `.env` e confere); consumo de RAM medido (`MemoryPeak` das unidades) e registrado; `docs/AMBIENTES.md`",
   "adversário procura qualquer caminho pelo qual homologação alcança dado de produção (DSN, bucket, token) e tenta abrir homolog sem a senha básica",
   ["arquiteto", "backend", "testador", "adversario"], "P", ["L0-01-repo"], "usuario")

# ===== 2. Appliance ==================================================================================
it("L7-11-a-appliance-licenca", 4,
   "licença do appliance como arquivo JSON assinado (ed25519, mesma raiz de L7-16) com: identificador do inquilino, validade, limites (usuários, TB, inquilinos), módulos habilitados; verificada na partida e uma vez por dia; NÃO telefona para casa; vencida → modo somente-leitura com aviso no painel 30 dias antes; nunca apaga nem bloqueia exportação do dado (o dado é do cliente). Modelo: arquivo de autorização e recurso `licenses` do Portal",
   "`plat licenca instalar <arquivo>` aceita só assinatura válida; e2e mostra o aviso a 30/7/0 dias (relógio simulado); com licença vencida, leitura e exportação (L7-25) continuam e escrita devolve 403 com mensagem; licença de outro inquilino é recusada; nenhuma chamada de rede na verificação (teste com rede desligada)",
   "adversário edita o JSON, muda a validade e reassina com chave própria; adianta o relógio; tenta usar licença de outro appliance",
   ["arquiteto", "backend", "adversario"], "M", ["L7-16-assinatura-pacote", "L7-33-modo-somente-leitura", "L7-25-exportacao-inquilino"], "esri", pai="L7-11-appliance-cliente",
   fontes=["REST-portal-licenses", "E11-disconnected"])

it("L7-11-b-appliance-sem-internet", 4,
   "o appliance funciona sem internet depois de instalado: nenhum recurso de CDN externo (o adversário T1 já pegou o Swagger UI vindo de CDN), mapa-base local em PMTiles (recorte aberto do OSM/Natural Earth incluído no pacote, item externo proposto L2-01-a), fontes de letra e bibliotecas vendorizadas, conectores externos (Sentinel, WMS de terceiros) desligados com mensagem explícita e não com erro; CA interna do cliente aceita pelo nginx e pelos serviços; modelo: 'configure a disconnected deployment' do Portal",
   "teste sobe o compose numa rede docker `--internal` (sem saída) e roda o e2e inteiro: 0 pedido a host externo (proxy de captura conta = 0), 0 erro de console, mapa-base aparece; lista `docs/APPLIANCE.md` do que NÃO funciona offline (conectores) com a mensagem exata que a tela mostra",
   "adversário instala com rede desligada e lista cada função que quebra, cada recurso que tenta sair, cada mensagem de erro em vez de aviso",
   ["arquiteto", "frontend", "backend", "adversario"], "M", ["L7-01-a-compose-perfis", "L2-01-a-basemap-local-pmtiles"], "esri", pai="L7-11-appliance-cliente",
   fontes=["E11-disconnected"])

it("L7-11-c-telemetria-opcional", 4,
   "telemetria do appliance DESLIGADA por padrão e opt-in explícito do administrador: envia uma vez por dia versão, saúde dos componentes, contagens agregadas (itens, usuários, GB), nunca nome, nunca geometria, nunca conteúdo; texto do que é enviado mostrado na tela antes de ligar; chave própria por appliance; endpoint nosso registra e alimenta o painel de suporte",
   "com telemetria desligada, 0 pedidos de rede (mesmo teste de L7-11-b); ligada, o JSON enviado é idêntico ao que a tela mostrou (teste compara); o receptor (na casa) recusa chave desconhecida; `docs/APPLIANCE.md` lista os campos",
   "adversário liga a telemetria, captura o tráfego e procura qualquer campo além dos listados; tenta enviar com chave de outro appliance",
   ["backend", "adversario"], "P", ["L7-11-b-appliance-sem-internet"], "spec", pai="L7-11-appliance-cliente")

# ===== 3. Carga e capacidade =========================================================================
it("L7-02-a-k6-cenarios", 3,
   "k6 instalado (binário do GitHub, não há pacote no apt do Ubuntu) e cenários reproduzíveis em `tests/carga/`: (1) navegação — 100 usuários virtuais pedindo tiles vetoriais (Martin) e raster (TiTiler via nginx) de uma área do dado demo; (2) consulta — FeatureServer `query` com where e paginação; (3) edição — 20 editores em `applyEdits` concorrentes sobre a mesma camada; thresholds no próprio script (p95 tile quente < 200 ms; erro < 1 %); relatório JSON gravado em `tests/medidas/`",
   "`make carga` roda os 3 cenários contra homologação e sai 0 com thresholds verdes; números publicados: p50/p95/p99 por cenário, tiles/s, HIT/MISS do cache nginx (cabeçalho X-Cache já existe na prova), conexões Postgres no pico (`pg_stat_activity`), RAM dos serviços (`MemoryPeak`); comparação com o medido na prova do pipeline (1.080 tiles/s quente, 16-65 frio) registrada",
   "adversário repete com cache frio (`proxy_cache_bypass` e versão nova no caminho) e publica os dois números; roda o cenário de edição e confere no banco que nenhuma edição se perdeu (contagem esperada = contagem real)",
   ["backend", "testador", "adversario"], "M", ["L7-31-ambiente-homologacao", "L2-04-servicos-esri-ogc", "L1-02-tiles-token"], "casa", pai="L7-02-carga",
   fontes=["K6", "K6-thresholds", "K6-scenarios", "REST-applyedits", "GS-controlflow"])

it("L7-02-b-pool-e-limites-por-inquilino", 3,
   "ajuste medido de pool e limites: pool psycopg2 (8 por worker hoje) × pgbouncer 1.25 em modo transação (exige `SET LOCAL` para o contexto RLS — já é assim no ADR 0001) decidido por medição no cenário de edição; limite de concorrência POR INQUILINO no nginx (`limit_conn` por token) e na API (semáforo por inquilino nos jobs) para que um inquilino não derrube os outros — equivalente ao control-flow do GeoServer (ows.global, por usuário/IP)",
   "medição A/B (pool interno × pgbouncer) com os mesmos cenários e números lado a lado; decisão escrita no ADR com o número; teste 'inquilino barulhento': 1 inquilino a 500 req/s não faz o p95 do outro passar de 2× o valor em repouso; conexões nunca passam de `max_connections` − 20 (alarme em L7-06-b)",
   "adversário abre 1.000 conexões ociosas com um token e mede o outro inquilino; qualquer 5xx no inquilino vítima = refutado",
   ["dados", "backend", "adversario"], "M", ["L7-02-a-k6-cenarios"], "geoserver", pai="L7-02-carga", fontes=["PGBOUNCER", "GS-controlflow", "NGINX-limit", "REST-server-props"])

it("L7-17-capacidade-planejamento", 3,
   "modelo de capacidade alimentado pela medição por inquilino (L7-09-a) e pelos números de carga: `plat capacidade` projeta, por recurso (disco Garage, disco Postgres, tiles/s de origem, conexões, RAM, GPU-h), quando a máquina chega a 70 % e 90 % mantendo a tendência dos últimos 90 dias; relatório mensal; alarme em 70 % (L7-06-b); é a base do 'quando entra a 2ª máquina' da spec 18.2",
   "relatório gerado do banco (nenhum número digitado) com data prevista de saturação por recurso e o comando que a produziu; teste com série sintética conhecida acerta a data; painel Grafana com as 6 curvas e as linhas de 70/90 %",
   "adversário injeta 30 dias de crescimento sintético e confere que a previsão muda e o alarme dispara; procura número no relatório que não venha de tabela",
   ["backend", "adversario"], "P", ["L7-09-a-medidor-diario", "L7-06-d-paineis"], "spec")

it("L7-18-custo-por-inquilino", 3,
   "custo por inquilino MEDIDO e reconciliado com a fatura: disco (GB-mês no Garage e no Postgres por schema/bucket), saída de rede (bytes por token no log do nginx; CDN pelo painel/API da CDN), CPU-segundo dos jobs, GPU-segundo, chamadas de API; rateio do custo fixo declarado; relatório mensal em R$ com as premissas à vista (câmbio datado, preço da máquina datado) — o 'custo marginal' da spec 17.3 deixa de ser estimativa",
   "`plat custo --mes` gera CSV/PDF por inquilino; soma dos rateios = custo total da fatura do mês (diferença ≤ 1 %); toda premissa (preço, câmbio) está em `plat.premissa_custo` com data e fonte; teste com fatura sintética",
   "adversário compara o GB-mês do relatório com `du`/admin API do Garage e `pg_total_relation_size` no último dia do mês; divergência > 2 % = refutado",
   ["backend", "adversario"], "M", ["L7-09-a-medidor-diario"], "spec")

# ===== 4. Segurança ==================================================================================
it("L7-03-e-cabecalhos-csp-tls", 2,
   "cabeçalhos completos e testados por rota: HSTS (max-age 1 ano; preload é decisão do dono), CSP com nonce por resposta e `script-src 'self'` (Swagger/portal de API servidos localmente, sem CDN), `frame-ancestors` por inquilino (embutir app em site do cliente é caso de uso: lista de origens por inquilino), Permissions-Policy, COOP/CORP, Referrer-Policy, X-Content-Type-Options (já), Cache-Control por tipo; CORS com lista de origens por token; TLS no perfil intermediate da Mozilla, HTTP/2, OCSP stapling; `security.txt`; a Esri entrega CSP padrão `script-src 'self';` e cabeçalho nosniff — a paridade é superar isso",
   "`tests/api/test_cabecalhos.py` cobre TODAS as rotas do OpenAPI (parametrizado) e as estáticas; nenhuma resposta sem CSP; `web/` sem `<script>` inline sem nonce e sem `onclick=` (teste lê os arquivos); relatório do Mozilla Observatory ≥ A registrado (comando `curl` da API do Observatory) e do teste TLS externo; e2e do app com CSP ativa = 0 erro de console; embutir em origem autorizada funciona e em não autorizada é bloqueado (e2e)",
   "adversário injeta `<img onerror>` num nome de camada e num popup, tenta carregar script externo, tenta iframe de origem não listada, testa TLS 1.0/1.1 e cifras fracas",
   ["backend", "frontend", "testador", "adversario"], "P", ["L2-01-mapa-web"], "esri", pai="L7-03-seguranca",
   fontes=["REST-server-secconfig", "REST-server-props", "OWASP-CSP", "MDN-CSP", "MDN-HSTS", "MDN-PP", "MDN-COOP", "MDN-CORP", "MDN-CORS", "MOZ-OBS", "MOZ-TLS", "SSLLABS", "RFC9116"])

it("L7-03-b-rate-limit-abuso", 2,
   "limitação de taxa em três camadas: nginx por IP (zonas `perip`/`authip` já existem na casa; zonas próprias `plat_login`, `plat_api`, `plat_tiles`) → API por token/inquilino (janela deslizante no Postgres ou em memória por worker, 429 com Retry-After conforme RFC 6585) → fail2ban com jail para 401/429 repetidos (fail2ban 1.0.2 já roda aqui com 3 jails); bloqueio progressivo de login já previsto no L0-02 (5 tentativas/15 min, régua Esri); limites diferentes por plano (L7-09-b)",
   "teste automatizado dispara 200 logins errados e confere 429 e depois o banimento no fail2ban (`fail2ban-client status plat`); tile acima do limite do plano devolve 429 sem derrubar o cache; limite por inquilino não afeta outro (teste cruzado); todos os limites documentados em `docs/SEGURANCA.md` com número e comando de teste",
   "adversário distribui o ataque em 50 IPs contra um token (o limite por token tem de segurar) e num IP contra 50 tokens (o limite por IP tem de segurar)",
   ["backend", "testador", "adversario"], "P", ["L0-02-tenant-auth", "L1-02-tiles-token"], "casa", pai="L7-03-seguranca", fontes=["NGINX-limit", "RFC6585", "GS-controlflow"])

it("L7-03-c-ssrf-conectores", 2,
   "SSRF fechado em todo lugar onde o usuário fornece URL (conectores WMS/WMTS/WFS/OGC/ArcGIS REST do L6-02, STAC externo do L1-03, webhooks do L7-08-c, geocodificador externo, imagem por URL): uma única função `url_segura()` que resolve DNS, recusa IP privado/loopback/link-local/metadados (169.254.169.254), IPv6 equivalentes, esquemas ≠ https/http, portas fora da lista, e re-resolve após cada redirecionamento (máx. 3); saída de rede dos workers por proxy de saída com lista de destinos (nginx/squid local) quando em appliance; a Esri lista `allowedProxyHosts`/`httpProxy*` como o mesmo controle",
   "suíte de ataques em `tests/seguranca/test_ssrf.py` (30 casos: `http://127.0.0.1:8150/saude`, `http://[::1]`, `http://0x7f000001`, DNS que resolve para privado, redirecionamento 302 para privado, `file://`, `gopher://`) todos bloqueados com o mesmo erro; grep prova que toda chamada `httpx`/`urllib` de URL do usuário passa por `url_segura()` (teste estático)",
   "adversário com token de editor cadastra conector apontando para `/saude` interno, para o Garage admin :3903, para o Prometheus :9090 e para o metadata endpoint da nuvem; qualquer byte devolvido = refutado",
   ["backend", "adversario"], "M", ["L6-02-conectores-vivos", "L7-08-a-webhooks-eventos"], "esri", pai="L7-03-seguranca", fontes=["OWASP-SSRF", "REST-portal-sysprops", "REST-portal-secupdate", "GS-security"])

it("L7-03-d-injecao-consulta", 2,
   "injeção em consulta fechada por construção, não por filtro: `where` do FeatureServer e `filter` OGC (CQL2) passam por parser próprio → AST → SQL parametrizado com lista branca de colunas e funções (o parser pertence a L2-04; item externo proposto L2-04-a); `outFields`, `orderByFields`, `groupByFieldsForStatistics`, `outStatistics` validados contra o esquema da camada; nomes de tabela/coluna sempre por `psycopg2.sql.Identifier`; a Esri chama isso de standardized queries (padrão true) e `featureServiceXSSFilter=input`",
   "suíte `tests/seguranca/test_injecao.py` com ≥ 100 payloads (sqlmap tamper list, `1=1; DROP`, comentários, unicode, `pg_sleep`, funções de sistema, subconsulta em outStatistics) → todos 400 ou resultado correto, 0 execução; `grep` prova ausência de f-string/format em SQL com entrada do usuário (teste estático com `bandit`/`semgrep` regra própria); ZAP baseline sem alerta alto",
   "adversário roda sqlmap contra `query`, `applyEdits` e OGC `items?filter=` com token de visualizador e publica o log; qualquer leitura fora do inquilino ou fora da camada = refutado",
   ["backend", "testador", "adversario"], "M", ["L2-04-servicos-esri-ogc", "L2-04-b-parser-where-ast"], "esri", pai="L7-03-seguranca",
   fontes=["REST-featureservice", "E11-sec-bp", "REST-server-props", "BANDIT", "SEMGREP", "ZAP"])

it("L7-03-a-antivirus-upload", 2,
   "pipeline único de upload (vetor, raster, anexo, foto de campo, logotipo, CSV): tamanho por plano e por tipo; tipo por bytes mágicos (não por extensão) contra lista permitida por rota (paridade com `uploadFileExtensionAllowedList` da Esri: soe,sd,sde,odc,csv,txt,zshp,kmz,geodatabase); nome sanitizado e reescrito por id; nunca servido do mesmo host com `Content-Disposition: inline` (anexos por subcaminho com CSP `sandbox`); SVG só após sanitização (sem script/foreignObject/handlers); zip-bomb (razão de expansão e contagem de entradas); antivírus ClamAV 1.5 (apt) por `clamd` OPCIONAL com quarentena e registro — opcional porque custa RAM (~1,3 GB de assinaturas) e o appliance pode não ter",
   "`tests/seguranca/test_upload.py`: EICAR é recusado quando clamd está ligado e o evento aparece na trilha (L7-20); SVG com `<script>` sai sem o script; zip com 1 GB de zeros é recusado; `.exe` renomeado para `.tif` é recusado pelos bytes; arquivo 1 byte acima do plano = 413 antes de ler o corpo inteiro (medido pelo tráfego); documento lista tipos por rota",
   "adversário sobe polyglot (GIF+HTML), SVG com `xlink:href` javascript, shapefile com `.dbf` malformado que estoura o GDAL, KMZ com 10 mil entradas, e anexo `.html` que tenta ser aberto inline",
   ["backend", "testador", "adversario"], "M", ["L0-04-ingest-vetor", "L1-01-ingest-raster", "L2-03-edicao"], "esri", pai="L7-03-seguranca",
   fontes=["REST-server-props", "OWASP-UPLOAD", "CLAMAV", "CLAMAV-scan"])

it("L7-03-f-dependencias-cve-log-correcoes", 2,
   "varredura de dependência no `make check` e diária por timer: `pip-audit` (venv), `osv-scanner` (requirements + package-lock dos vendors), `trivy` nas imagens do compose, `gitleaks` no histórico; resultado vai para `plat.vulnerabilidade` e gera `docs/CORRECOES.md` (o 'log de correções' que a spec 8 e 17.4 prometem: CVE, componente, versão corrigida, data da publicação, data da correção, ≤ 48 h) — nunca texto digitado; página `/status` mostra o último ciclo",
   "timer roda e grava; CVE sintética (pacote antigo colocado de propósito em homologação) aparece no log em ≤ 24 h e some quando corrigida; `docs/CORRECOES.md` regenerado só por script (cabeçalho com sha da execução); `make check` reprova com CVE alta sem exceção registrada em `SEGURANCA.md` (exceção tem prazo)",
   "adversário instala pacote com CVE conhecida em homologação e cronometra até aparecer; procura no log de correções qualquer linha sem comando que a produziu",
   ["backend", "adversario"], "P", ["L0-01-repo"], "spec", pai="L7-03-seguranca", fontes=["PIP-AUDIT", "OSV", "TRIVY", "GITLEAKS", "GS-advisories", "ESRI-patches"])

it("L7-03-g-asvs-nivel2-pentest", 3,
   "OWASP ASVS 5.0 (estável desde 30/05/2025) nível 2 como checklist: `docs/SEGURANCA.md` gerado de `docs/asvs.yaml` com cada requisito marcado `teste:<caminho>` | `evidencia:<comando>` | `n.a.:<motivo>`; checklist de pentest (WSTG) executada internamente com ZAP baseline + full scan autenticado em homologação; relatório com achados, correções e o que fica aberto; o teste externo anual (spec 8) é decisão/compra do dono — registrar como pendente, nunca como feito; paridade com o `serverScan.py` da Esri: `scripts/varredura_seguranca.py` gera relatório HTML equivalente",
   "≥ 90 % dos requisitos ASVS L2 aplicáveis com teste ou evidência; 0 marcado 'feito' sem caminho; ZAP full scan em homologação sem alerta alto aberto; `scripts/varredura_seguranca.py` roda contra a URL e lista o que está fora da política (HTTPS, cabeçalhos, diretório de serviços, versões expostas); relatório datado em `docs/PENTEST_<data>.md`",
   "adversário com instrução de invadir por 1 turno inteiro (autenticado como visualizador de um inquilino) tenta elevar privilégio, ler outro inquilino, executar código, exfiltrar segredo; escreve o que conseguiu e o que não; qualquer sucesso = refutado",
   ["backend", "testador", "adversario"], "G", ["L7-03-e-cabecalhos-csp-tls", "L7-03-b-rate-limit-abuso", "L7-03-c-ssrf-conectores", "L7-03-d-injecao-consulta", "L7-03-a-antivirus-upload", "L7-03-f-dependencias-cve-log-correcoes", "L7-19-segredos-e-certificados"], "esri", pai="L7-03-seguranca",
   fontes=["ASVS", "ASVS-rel", "WSTG", "ZAP", "E11-scan", "ESRI-trust"])

it("L7-19-segredos-e-certificados", 2,
   "segredos fora do `.env` em texto: `LoadCredential=` do systemd (Ubuntu 24.04, systemd 255) entrega `PLAT_SECRET`, senha do banco, chaves S3 do Garage e token admin do Garage como arquivos em `/run/credentials/`; `.env` fica só com o que não é segredo; rotação com dupla chave (`PLAT_SECRET` + `PLAT_SECRET_ANTERIOR` por 24 h, sessões sobrevivem); rotação da senha do banco (`ALTER ROLE` + reinício em cadeia sem erro); rotação das chaves S3 por inquilino (Garage cria nova, troca, revoga); token admin do Garage da prova está em claro em `garage.toml` — corrigir; certificados: certbot já renova por timer; alarme 14 d antes (blackbox exporter); CA própria do cliente no appliance",
   "`plat segredo rotacionar <nome>` para cada um dos 5 segredos, com teste que prova que o valor antigo deixa de funcionar e o serviço não cai (0 erro 5xx durante a rotação, medido pelo k6 curto); `grep -r` do repositório e do journal por qualquer segredo = 0; `.env` sem segredo (teste lê); `docs/RUNBOOKS/segredos.md`",
   "adversário lê `/proc/<pid>/environ`, o journal, o `.env`, o `garage.toml` e o histórico do git à procura de qualquer segredo; qualquer um em claro fora de `/run/credentials` = refutado",
   ["arquiteto", "backend", "adversario"], "M", ["L0-01-repo"], "casa", fontes=["SYSTEMD-creds", "SYSTEMD-exec", "CERTBOT", "LE-limits", "PROM-blackbox", "GARAGE-admin", "SOPS"])

it("L7-20-trilha-auditoria", 2,
   "trilha de auditoria de negócio (diferente do log de acesso): tabela `plat.auditoria` append-only (sem UPDATE/DELETE para `plat_app`, trigger que impede) escrita na MESMA transação de login, logout, criação/edição/compartilhamento/exclusão de item, mudança de permissão, exportação, ato administrativo e acesso a camada `pessoal` (L7-12-a); campos: quando, inquilino, usuário/token, ação, recurso, antes/depois resumidos, req_id, IP; `pgaudit` (já carregado nesta máquina) para DDL; exportação CSV/JSON por período e envio a SIEM (syslog/CEF opcional); tela Auditoria para admin; paridade com audit logs do Portal (retenção herdada dos logs; SIEM)",
   "toda rota de escrita do OpenAPI gera linha (teste percorre o OpenAPI e confere); tentativa de UPDATE/DELETE em `plat.auditoria` como `plat_app` falha; retenção configurável (padrão 2 anos; Esri usa 90 d para logs) com expurgo por pg_cron; exportação bate com contagem; e2e da tela com filtro por usuário e período",
   "adversário edita um item e tenta apagar a própria trilha (pela API, por SQL como plat_app, por expurgo prematuro); qualquer linha sumida = refutado",
   ["dados", "backend", "adversario"], "M", ["L0-02-tenant-auth", "L0-03-catalogo"], "esri", fontes=["E11-audit", "PGAUDIT", "REST-server-editlog"])

# ===== 5. Observabilidade ===========================================================================
it("L7-06-a-metricas-exporters", 2,
   "métricas Prometheus em todos os componentes: API e worker com `prometheus_client` (padrão da casa: a API em :8002 já expõe assim) — `plat_http_requests_total{rota,status,tenant}`, histograma de latência por rota, `plat_jobs_*`, `plat_tiles_*` por origem/cache; Martin (nativo), TiTiler (instrumentator), Garage (`:3903/metrics` já ligado, com `metrics_token`), nginx (`prometheus-nginx-exporter` 1.1.0 apt + stub_status), Postgres (`postgres_exporter` 0.15.0 apt, consultas próprias para `pg_stat_replication`, tamanho por schema, conexões por inquilino), node (já roda em :9100); scrape pelo Prometheus da casa em `/opt/monitoring` (só acrescentar job; nunca substituir) e, no appliance, pelo perfil `observabilidade` do compose com os MESMOS arquivos; rótulo `tenant` só em métricas de baixa cardinalidade, nunca token",
   "`curl :8150/metrics` e de cada exporter devolve 200 com as famílias listadas; Prometheus `targets` todos `up`; teste conta cardinalidade (≤ 5.000 séries por serviço com 50 inquilinos sintéticos); `X-Req-Id` propagado para Martin/TiTiler (cabeçalho chega no log deles); `docs/OBSERVABILIDADE.md` lista cada métrica com significado",
   "adversário cria 500 tokens e faz 1 pedido com cada um: a cardinalidade das séries não pode crescer com o número de tokens; procura métrica que devolve número fixo",
   ["backend", "adversario"], "P", ["L0-05-jobs", "L1-02-tiles-token"], "casa", pai="L7-06-observabilidade",
   fontes=["PROM-client", "PROM-node", "PROM-pg", "PROM-nginx", "GARAGE-mon", "GARAGE-admin", "MARTIN", "TITILER", "E11-monitor", "REST-server-usage-settings"])

it("L7-06-b-alertas", 2,
   "regras de alerta e roteamento: Alertmanager 0.26 (apt) ou alerting do Grafana — decidido por medição de simplicidade no appliance (um serviço a menos); regras versionadas em `deploy/alertas.yml`: disco > 85 % aviso / > 95 % crítico (a Esri usa `diskSpaceThresholdGB` 5), RAM disponível < 2 GB, fila com job > 30 min, 5xx > 1 % em 5 min, p95 de tile > 500 ms por 10 min, certificado < 14 d, backup atrasado > 26 h, drill do mês não executado, réplica com atraso > 5 min ou parada, Martin/TiTiler/Garage/worker `up == 0` por 2 min, alvo Prometheus caído; canais: e-mail (SMTP da organização, modelo `emailsettings` do Portal), webhook (ntfy/Slack-compatível), e o próprio painel do produto (banner para admin); silêncio por manutenção ligado ao modo somente-leitura",
   "cada regra tem teste que a dispara de verdade em homologação (encher disco com `fallocate` num volume de teste, parar o Martin, atrasar o backup) e o alerta chega ao canal de teste em ≤ 2 min, com evidência de hora de envio; `amtool check-config` verde; `docs/RUNBOOKS/alertas.md` liga cada alerta ao runbook",
   "adversário derruba o Martin sem avisar e cronometra; depois derruba o próprio Alertmanager e confere que o Prometheus/Grafana acusa (alerta do alertador)",
   ["backend", "adversario"], "P", ["L7-06-a-metricas-exporters"], "esri", pai="L7-06-observabilidade", fontes=["PROM-alert", "PROM-am", "GRAFANA-alert", "REST-portal-email", "REST-server-props", "REST-portal-sysprops"])

it("L7-06-c-logs-consulta-req-id", 2,
   "logs consultáveis: JSON por linha no journal já existe; nível ajustável em tempo de execução por rota/componente sem reinício (`plat log nivel DEBUG --por 10min`, equivalente ao `logLevel` do Server que vai de OFF a DEBUG com padrão WARNING); retenção 90 dias (padrão `maxLogFileAge` da Esri) no journal (`SystemMaxUse` por unidade) e opcionalmente Loki (perfil do compose) com rótulos serviço/inquilino/nível; `plat logs --req-id <id>` reúne as linhas de nginx, API, worker, Martin, TiTiler e Postgres do mesmo pedido (o `X-Req-Id` propagado em L7-06-a; Postgres via `application_name` = req_id curto); tela Logs para admin do inquilino (só as linhas dele, via RLS de `plat.log_acesso`)",
   "um pedido sintético de tile com erro forçado produz linhas nos 4 serviços e `plat logs --req-id` mostra as 4 em ordem; mudar nível em runtime muda o volume (medido); retenção comprovada (`journalctl --disk-usage` após carga); admin de um inquilino não vê linha de outro (teste cruzado); nenhum segredo nem token completo em log (teste procura os valores)",
   "adversário faz pedido com `X-Req-Id` forjado de outro inquilino e tenta ler as linhas; procura senha/token/segredo em 24 h de log",
   ["backend", "adversario"], "P", ["L7-06-a-metricas-exporters"], "esri", pai="L7-06-observabilidade", fontes=["REST-server-editlog", "E11-portal-logs", "LOKI", "PG-logging", "QGIS-server-config"])

it("L7-06-d-paineis", 3,
   "painéis Grafana provisionados por arquivo (`deploy/grafana/*.json`), nunca editados à mão: Visão geral (10 métricas: p95 por rota, tiles/s, HIT %, fila, conexões, disco, RAM, 5xx, usuários ativos 24 h, jobs), Por inquilino (seletor), Banco (réplica, WAL, tabelas maiores, consultas lentas via pg_stat_statements), Objetos (Garage por bucket), Backup e drill (última execução, duração, tamanho); no hospedado entram no Grafana da casa (127.0.0.1:3000, provisioning) e no appliance no perfil `observabilidade`",
   "os 5 painéis carregam sem 'No data' contra homologação com carga curta (captura playwright de cada um em `tests/e2e/capturas/`); provisioning idempotente (subir 2× = mesmo uid); todo painel referencia só métricas que existem (teste percorre os JSON e consulta o Prometheus)",
   "adversário apaga um painel pela UI e confere que o provisioning o recria; procura painel com consulta que devolve vazio",
   ["backend", "frontend", "adversario"], "P", ["L7-06-a-metricas-exporters"], "casa", pai="L7-06-observabilidade", fontes=["GRAFANA-prov", "PG-pgstat"])

it("L7-21-pagina-status", 3,
   "COMPLEMENTA o `/status` do L0-06-e (estado atual, fila, backup, drill, disco, certificado, histórico de 90 d): acrescenta o estado por componente do health profundo (L7-34), disponibilidade dos últimos 12 meses por mês (calculada da série do Prometheus e persistida em `plat.disponibilidade_mensal` para sobreviver à retenção de 15 d do Prometheus da casa), incidentes abertos e passados (`plat.incidente` do L7-22), último backup e último drill com resultado (L7-24), último ciclo de correções (L7-03-f), versão; formato pensado para responder 'fica no ar?' e 'e se perder tudo?' da spec 8; avaliados uptime-kuma/gatus/upptime — descartados porque o número tem de sair do mesmo Prometheus e do mesmo banco que o resto",
   "e2e da página; número de disponibilidade do mês = 1 − (minutos com `up == 0` do componente / minutos do mês), recalculado por timer e conferível com consulta PromQL publicada na própria página; incidente sintético aparece e é fechado; página responde mesmo com o banco em erro (versão estática em cache com carimbo de hora)",
   "adversário derruba a API por 3 min e confere que os 3 min aparecem no mês; tenta abrir a página sem o link (noindex e caminho não-adivinhável ou subdomínio decidido pelo dono)",
   ["backend", "frontend", "adversario"], "P", ["L0-06-e-status", "L7-34-saude-profunda", "L7-06-a-metricas-exporters", "L7-24-drill-restauracao", "L7-22-sla-e-incidentes"], "spec", fontes=["UPTIME-KUMA", "GATUS", "UPPTIME", "E11-manutencao"])

it("L7-22-sla-e-incidentes", 3,
   "SLA e processo de incidente como dado, não como promessa: `docs/SLA.md` declara disponibilidade mensal, RTO e RPO SOMENTE com número medido (disponibilidade dos últimos 3 meses do `/status`; RTO do ensaio de failover L7-07-c; RPO do WAL em L7-23) e o crédito por faixa (spec 17.4: 99,5 % com crédito só com a 2ª máquina); severidades S1-S4 com tempo de resposta e de atualização; `plat incidente abrir/atualizar/fechar` grava `plat.incidente` (aparece no /status e vira post-mortem em `docs/INCIDENTES/<data>.md` gerado); a Esri não declara SLA para Enterprise on-premises (é do cliente) — aqui é o que se vende",
   "`docs/SLA.md` é gerado por script a partir das tabelas (cabeçalho com data e comando; 0 número digitado); incidente sintético percorre abrir → atualizar → fechar → post-mortem gerado; teste falha se algum número do SLA não tiver origem em `tests/medidas/` ou em tabela",
   "adversário procura em `docs/SLA.md` ou na página de status um número sem medição que o sustente (RTO 'declarado' sem ensaio = refutado)",
   ["gerente", "backend", "cronista", "adversario"], "P", ["L7-07-c-ensaio-failover", "L7-23-pgbackrest-pitr", "L7-21-pagina-status"], "spec", fontes=["E11-perda-x-parada", "RFC9110"])

# ===== 6. Backup, restauração, alta disponibilidade ==================================================
it("L7-23-pgbackrest-pitr", 3,
   "backup físico com PITR: pgBackRest 2.59 (apt) com `repo1` S3 no Garage (repo-type=s3, compatibilidade conferida) e `repo2` fora da máquina (B2 ou Storage Box; B2 não tem região na América do Sul — registrar para o perfil de soberania); `archive_mode=on` (hoje OFF nesta máquina, `wal_level=replica` já) com `archive-push` assíncrono; full semanal + incremental diário + WAL contínuo; retenção 2 full; `pgbackrest check` e `verify` por timer; cifra do repositório (`repo-cipher-type`). DECISÃO DE ESCOPO (ver CONCEITO C3): pgBackRest opera o CLUSTER inteiro — nesta máquina o cluster `iagro_sat` tem 543 GB de vários projetos e 17 GB livres, logo o físico só é possível com repositório fora da máquina e é decisão do dono (D21); no appliance e na 2ª máquina o cluster é só o plat e o físico é obrigatório. O lógico por inquilino (L7-25) existe nos dois casos. Modelo Esri: webgisdr full/incremental, incremental exige PITR ligado no Data Store",
   "em homologação com cluster dedicado (contêiner Postgres do compose): full + incremental + WAL arquivados no Garage; `pgbackrest info` mostra os dois repositórios; restauração PITR para um instante entre dois commits sintéticos recupera exatamente o estado (linha inserida antes existe, depois não); RPO medido = intervalo real entre `archive_timeout` e o último WAL enviado (registrado em `tests/medidas/`); timers systemd para backup, check e expire; alerta de backup atrasado (L7-06-b) testado",
   "adversário apaga o diretório de dados do Postgres de homologação e restaura só com o que está no Garage/B2, cronometrando (RTO do backup, distinto do RTO da réplica); depois corrompe um arquivo do repositório e confere que `verify` acusa",
   ["dados", "backend", "adversario"], "G", ["L7-31-ambiente-homologacao", "L7-01-a-compose-perfis"], "esri",
   fontes=["PGBR-guide", "PGBR-config", "PGBR-command", "PG-archiving", "E11-webgisdr", "E11-datastore-backup", "E11-backup-bp", "GARAGE-s3", "B2-pricing", "B2-regions"],
   notas="Estado medido 05/09: wal_level=replica, archive_mode=off, 0 réplicas, ssl on, scram-sha-256, pgaudit+pg_cron carregados; timers de backup lógico por schema existem para 3 SIGs da casa (03:15/03:35/03:45); o backup diário do servidor foi DESLIGADO em 27/05/2026 por disco cheio.")

it("L7-24-drill-restauracao", 3,
   "drill de restauração mensal, scriptado e publicado: timer `plat-drill.timer` (dia 1, 04:00, depois do backup) restaura o último backup lógico do schema `plat` num banco temporário (padrão da casa: `restore_test.sh` do SIG de teste interno) e, onde houver pgBackRest, o físico numa instância temporária; confere `COUNT(*)` de TODAS as tabelas com `tenant_id` contra produção (não amostra), sha256 de 1 % dos objetos do Garage escolhidos por semente registrada, e abre a aplicação contra o banco restaurado com um e2e curto; grava `plat.drill` (quando, o que, duração, divergências) e publica no `/status`; a Esri recomenda 'restore drill em cadência semirregular' — aqui é mensal e público",
   "o drill roda por timer e o resultado aparece no `/status` com data; divergência sintética (linha inserida em produção após o backup) é detectada e classificada como esperada pela janela; falha real (tabela faltando) marca o drill como REPROVADO e dispara alerta; `docs/RUNBOOKS/restaurar.md` com o comando manual e o tempo medido",
   "adversário restaura o backup mais recente em schema à parte e compara `COUNT(*)` de todas as tabelas com `tenant_id` (refutação do L0-06); depois apaga uma tabela do backup e confere que o drill do mês seguinte (rodado à força) reprova",
   ["dados", "backend", "adversario"], "P", ["L0-06-a-dump-logico", "L0-06-backup-status", "L7-23-pgbackrest-pitr"], "casa", fontes=["E11-backup-bp", "SYSTEMD-timer"])

it("L7-25-exportacao-inquilino", 3,
   "COMPLEMENTA o L0-06-d (que já gera GeoPackage + JSON do catálogo + zip por item + manifesto): acrescenta o que nasce depois da fundação e o escrow agendado — itens STAC e COGs (L1), mapas/apps/painéis/formulários/fluxos/redes no esquema JSON do L5/L4, metadados ISO (L0-09); agendamento semanal para o bucket DO CLIENTE (chave S3 fornecida por ele: escrow prático da spec 17.4); reimportação completa em inquilino novo. Formato: GeoPackage (todas as camadas vetoriais, domínios, relações), COGs e itens STAC (catálogo estático), JSON de mapas/apps/painéis/formulários/redes no esquema documentado do L0-03/L5, usuários/grupos/permissões, metadados ISO; gerada como job (L0-05), gravada no bucket do inquilino e opcionalmente no bucket DELE (chave S3 fornecida por ele: escrow prático da spec 17.4); reimportação em inquilino novo funciona (é o mesmo caminho da migração L2-08 e do dado de demo); paridade com `exportSite` (.portalsite) do Portal, mas em formato aberto e por inquilino",
   "botão 'Exportar meu inquilino' e `plat exportar <slug>` produzem o pacote; `plat importar` num inquilino vazio recria tudo e o e2e do inquilino passa contra a cópia (contagens iguais, mapas abrem, tokens novos); agendamento semanal para bucket externo testado com um Garage secundário; tamanho e duração medidos para o inquilino demo",
   "adversário exporta, importa em outro inquilino e procura qualquer coisa que não voltou (camada, estilo, permissão, anexo, metadado); um item perdido = refutado",
   ["backend", "dados", "adversario"], "M", ["L0-06-d-exportar-inquilino", "L0-05-jobs", "L2-08-migracao-agol"], "esri", fontes=["REST-portal-export", "REST-portal-import", "GS-backup"])

it("L7-07-a-replica-postgres", 3,
   "réplica física em streaming (hot standby) na 2ª máquina ou, em homologação, num segundo contêiner: slot de replicação, `synchronous_commit` decidido por medição (assíncrono por padrão; síncrono só se o custo de latência medido for aceitável), `hot_standby_feedback`, monitoramento de atraso (bytes e segundos) no Prometheus, `pg_promote()` por script com trava de segurança (nunca dois primários: cerca por arquivo de estado + parada do antigo); Patroni avaliado e adiado (exige DCS de 3 nós; com 2 máquinas o failover é MANUAL e assumido como tal no SLA); `useROConnectionForQueries` da Esri 11.4 é o mesmo desenho: leitura na réplica",
   "réplica sobe e alcança o primário (`pg_stat_replication` state=streaming); atraso sob carga do k6 medido e < 5 s; leitura de tiles/consultas roteável para a réplica por configuração (`PLAT_DSN_LEITURA`) com teste que prova que escrita nunca vai para ela; `promover.sh` cronometrado (RTO do banco) e documentado; após promover, o antigo primário não aceita escrita (teste)",
   "adversário mata o primário com `kill -9` durante o k6 de edição e cronometra até a réplica promovida aceitar escrita; depois tenta religar o antigo primário e provar split-brain (duas escritas divergentes) — qualquer divergência = refutado",
   ["dados", "backend", "adversario"], "M", ["L7-23-pgbackrest-pitr"], "esri", pai="L7-07-alta-disponibilidade", fontes=["PG-standby", "PG-ha", "PATRONI", "REST-portal-sysprops", "E11-ha"])

it("L7-07-b-replica-garage", 3,
   "Garage com `replication_factor` 2 em dois nós (hoje 1 nó, rf=1 na prova) — 3 nós/rf=3 quando houver terceira máquina; layout com zonas; `garage repair`/scrub por timer; cotas por bucket mantidas; teste de perda de nó: leitura e escrita continuam; recuperação do nó re-sincroniza; `metrics_token` e `admin_token` em credencial (L7-19)",
   "cluster de 2 nós em homologação (2 contêineres); `garage status` mostra os dois; objeto gravado com um nó parado é lido depois que ele volta e o `scrub` não acusa; medição de tempo de re-sincronização de 10 GB; documento de operação `docs/RUNBOOKS/garage.md` (adicionar nó, trocar disco, ver layout)",
   "adversário desliga um nó, escreve 1.000 objetos, religa, e compara sha256 de todos nos dois nós; qualquer divergência não reparada pelo scrub = refutado",
   ["dados", "backend", "adversario"], "M", ["L7-01-a-compose-perfis"], "casa", pai="L7-07-alta-disponibilidade", fontes=["GARAGE-layout", "GARAGE-durability", "GARAGE-features", "GARAGE-upgrade"])

it("L7-07-c-ensaio-failover", 3,
   "ensaio de failover COMPLETO e cronometrado: primário (banco + API + Martin + TiTiler + nginx) morre sem aviso; procedimento: promover réplica (L7-07-a), religar serviços sem estado apontando para ela, trocar o destino (registro DNS com TTL 60 s ou IP flutuante do provedor — a Esri exige balanceador de terceiros; aqui é DNS/IP + Cloudflare para tiles), sair do modo somente-leitura; tudo em `failover.sh` com confirmação humana (2 máquinas = failover manual assumido); RTO e RPO medidos e publicados; volta ao normal (failback) também ensaiada; a mesma disciplina da Esri para patch em HA: nunca as duas máquinas ao mesmo tempo",
   "ensaio executado em homologação com 2 contêineres/2 hosts, gravado em `tests/medidas/L7-07-c.json`: RTO (do kill até o primeiro 200 em escrita), RPO (transações perdidas contadas com sequência sintética), passos e quem executou; `docs/RUNBOOKS/failover.md` e `failback.md`; alerta de 'primário caiu' (L7-06-b) foi o que iniciou o ensaio",
   "adversário mata o primário sem aviso num horário que só ele sabe e cronometra o gerente seguindo só o runbook; qualquer passo não escrito ou RTO acima do declarado no SLA = refutado",
   ["dados", "backend", "gerente", "adversario"], "M", ["L7-07-a-replica-postgres", "L7-07-b-replica-garage", "L7-33-modo-somente-leitura", "L7-26-cdn-tiles"], "esri", pai="L7-07-alta-disponibilidade",
   fontes=["E11-ha", "E11-ha-1maq", "E11-ha-patch", "E11-dr", "E11-perda-x-parada"])

# ===== 7. CDN e soberania ============================================================================
it("L7-26-cdn-tiles", 3,
   "CDN para tiles: hostname SEPARADO e proxied pela Cloudflare (`tiles-<x>.iagrointel.com`; o app continua DNS-only por D19) com Cache Rule 'cache everything' no prefixo (Free tem 10 regras), chave de cache sem query string, `Cache-Control: public, max-age=31536000, immutable` porque a versão vai no caminho (`/svc/<token>/<item>@<versao>/{z}/{x}/{y}`; objeto nomeado por sha256 já é o padrão da prova), purge por prefixo quando um item é revogado (100 prefixos por pedido), 404 curto para tile fora da cobertura; medição de HIT % e latência por PoP (`cf-cache-status`, `cf-ray`); regra de saída: acima de ~1 TB/mês de origem externa o ToS da Cloudflare pesa → Bunny (PoPs no Brasil, HMAC nativo) ou R2 como origem — decisão registrada com o número do mês; range de COG NÃO passa pela CDN (fica no cache `slice` do nginx, já configurado na prova)",
   "tile pedido 2× de fora devolve `cf-cache-status: HIT` na 2ª; revogar token → purge → 3ª chamada é 403 em ≤ 60 s (medido); HIT % após o k6 de navegação ≥ 80 % registrado; teste prova que nenhuma rota de API/app passa pela CDN (cabeçalho `server`); `docs/CDN.md` com os limites do plano, o gatilho de 1 TB e o comando de purge",
   "adversário revoga um token e martela a CDN com a URL antiga procurando um HIT servido após a revogação; tenta ler tile privado de outro inquilino pela CDN mudando só o token no caminho",
   ["backend", "raster", "adversario"], "M", ["L1-02-tiles-token"], "spec", fontes=["CF-default", "CF-rules", "CF-cc", "CF-purge-prefix", "CF-purge", "CF-workers", "BUNNY-docs", "BUNNY-net", "NGINX-slice", "RFC9111"])

it("L7-27-origem-br-soberania", 3,
   "perfil de implantação por região (spec D2): `residencia` é atributo da INSTALAÇÃO, não do inquilino — uma instalação por região (BR: este servidor é Vultr São Paulo; EU: Hetzner, ISO 27001 no escopo de todos os data centers); dado, backup e réplica nunca cruzam região; CDN só para tiles de camadas classificadas pública/interna (L7-12-a), nunca `pessoal`; Regional Services da Cloudflare (terminação TLS e cache só na região) é produto do plano Enterprise — logo, para exigência contratual de solo, a CDN é desligada para o inquilino ou a origem BR responde direto; B2 não tem região na América do Sul → repositório 2 do perfil BR é outro provedor com região BR ou Storage Box com cláusula; documento por inquilino `docs/RESIDENCIA_<slug>.md` gerado com IPs, provedores, países e prova (traceroute/whois datados)",
   "`plat residencia <slug>` gera o documento a partir da configuração real (nenhum campo digitado); teste confere que bucket, banco, réplica e backup do inquilino apontam para provedores da mesma região; inquilino marcado sem CDN nunca recebe `cf-cache-status` (teste externo); página interna explica as duas ofertas com os números de latência já medidos (195 ms SP↔Falkenstein)",
   "adversário procura, para um inquilino BR, qualquer byte que saia do país: cabeçalhos de CDN, IP de backup, réplica, e-mail de notificação, telemetria; um achado = refutado",
   ["arquiteto", "backend", "adversario"], "P", ["L7-26-cdn-tiles", "L7-23-pgbackrest-pitr", "L7-12-a-classificacao-retencao"], "spec",
   fontes=["CF-regional", "CF-dls", "CF-r2", "HETZNER-cert", "VULTR-docs", "B2-regions", "ANPD-transf", "LGPD"])

# ===== 8. SDK, portal de API, webhooks ===============================================================
it("L7-08-b-sdk-python", 3,
   "SDK Python `plat` gerado do OpenAPI 3.1 (`openapi-python-client`) mais camada ergonômica escrita à mão (`Plataforma(url, token)` → `.camadas`, `.itens`, `.mapas`, `.jobs.esperar()`, `.tiles.url()`, `.exportar()`), paginação e retentativa embutidas, erros como Problem Details (RFC 9457); 10 exemplos executáveis (`exemplos/*.py`) que rodam contra o inquilino demo e são TESTES; publicado no repositório (`sdk/python`) com versão casada com a API; paridade escrita contra ArcGIS API for Python (gis.content.search/add/publish, features.FeatureLayer.query/edit_features)",
   "`pip install ./sdk/python` e os 10 exemplos passam no `make check`; cobertura do SDK sobre o OpenAPI = 100 % das rotas (teste compara); regeneração do cliente a partir do OpenAPI atual não deixa diff (o gerado é reproduzível); tabela de paridade em `docs/PARIDADE.md`",
   "adversário usa o SDK com chave de escopo `leitura` para tentar escrita e com chave de outro inquilino; procura rota do OpenAPI sem método no SDK",
   ["backend", "cronista", "adversario"], "M", ["L2-04-servicos-esri-ogc", "L7-08-d-portal-api-chaves"], "esri", pai="L7-08-sdk-api-webhooks", fontes=["DEV-python", "OPENAPI-PY", "OAS31", "RFC9457"])

it("L7-08-c-sdk-js", 3,
   "SDK JavaScript (ES module, sem dependência, `fetch`) com o mesmo modelo do Python, mais ajudantes MapLibre (`plat.maplibre.fonte(item)` devolve a `source` pronta com token; `plat.maplibre.estilo(mapa)`), 10 exemplos HTML que rodam no navegador e são e2e; paridade escrita contra o ArcGIS Maps SDK for JavaScript (FeatureLayer, Map, view, Query)",
   "os 10 exemplos abrem no chromium do playwright com 0 erro de console e mostram mapa/dado (captura); geração do cliente base reproduzível; sem `?v=` em import de módulo (regra da casa); tabela de paridade",
   "adversário abre os exemplos com CSP ativa (L7-03-a) e procura erro; usa token revogado e confere a mensagem",
   ["frontend", "cronista", "adversario"], "M", ["L7-08-b-sdk-python", "L2-01-mapa-web"], "esri", pai="L7-08-sdk-api-webhooks", fontes=["DEV-js", "OPENAPI-GEN"])

it("L7-08-a-webhooks-eventos", 3,
   "webhooks por inquilino: assinatura em `plat.webhook` (URL https validada por `url_segura()`, eventos, segredo), eventos vindos da tabela de eventos de domínio `plat.evento` (item externo proposto L0-10, gravada na mesma transação da mudança) — item.criado/atualizado/apagado/compartilhado, feicao.criada/atualizada/apagada (por camada, como FeaturesCreated/Updated/Deleted da Esri), job.concluido/falhou, usuario.criado/removido, rede.tracado.concluido; entrega por worker com cabeçalhos Standard Webhooks (`webhook-id`, `webhook-timestamp`, `webhook-signature` HMAC-SHA256), corpo com `when`, `operation`, `source`, `id`, `properties` (mesmos nomes do payload Esri para facilitar migração), retentativa exponencial até 5 tentativas (régua Esri: 1-5) com tempo limite configurável, desativação automática após N falhas em janela (régua Esri) com aviso ao admin, log de entregas com resposta, reenvio manual, e alvo alternativo 'executar fluxo' (L5-02) além de URL",
   "e2e: criar webhook, editar feição, receptor de teste (servidor local) recebe em ≤ 5 s com assinatura válida (verificada pela biblioteca de referência do Standard Webhooks); receptor que devolve 500 vê 5 tentativas com intervalos crescentes e depois desativação + aviso; reenvio manual funciona; entrega é idempotente (mesmo `webhook-id`); nenhuma entrega para URL privada (SSRF); log de entregas por inquilino com RLS",
   "adversário forja entrega sem assinatura e com assinatura de outro segredo (o receptor de exemplo tem de recusar), cadastra URL interna, e repete uma entrega antiga (replay: timestamp fora de 5 min é recusado pelo receptor de exemplo)",
   ["backend", "adversario"], "M", ["L0-10-eventos-historico", "L0-05-jobs", "L7-03-c-ssrf-conectores"], "esri", pai="L7-08-sdk-api-webhooks",
   fontes=["E11-webhooks", "E11-webhook-payload", "REST-server-webhooks", "REST-server-webhook-settings", "REST-org-webhooks", "STDWEBHOOKS", "STDWEBHOOKS-gh", "STRIPE-wh", "FASTAPI-wh"])

it("L7-08-d-portal-api-chaves", 3,
   "portal de API servido localmente (Scalar ou Redoc vendorizados em `web/vendor`, sem CDN, com CSP): OpenAPI 3.1 navegável com descrição em português, exemplos por rota, botão 'experimentar' contra o inquilino demo com chave de demonstração de escopo `leitura`; chaves de API (o `token_servico` do L0-02) com escopos nomeados (leitura, edição, admin, tiles), expiração obrigatória (padrão 90 d, máx. 1 ano; a Esri: token máx. 14 d, chaves de API com expiração), restrição por origem/IP, último uso e contagem (alimenta a medição), revogação imediata; 20 exemplos executáveis (10 Python + 10 JS) referenciados no portal",
   "e2e do portal: navegar, executar um GET com a chave demo, ver a resposta; chave expirada → 401 com Problem Details; chave de escopo `leitura` em rota de escrita → 403; revogar → 403 em ≤ 5 s; nenhum recurso externo carregado (teste de rede); OpenAPI válido (validador) e com `x-plat-escopo` em toda rota (teste)",
   "adversário usa chave com escopo errado em cada rota do OpenAPI (varredura automática) e conta 200 indevidos; tenta chave sem expiração pela API",
   ["backend", "frontend", "cronista", "adversario"], "P", ["L0-02-tenant-auth"], "esri", pai="L7-08-sdk-api-webhooks", fontes=["DEV-apikey", "E11-token-exp", "REDOC", "SCALAR", "OAS31", "RFC9457"])

# ===== 9. Medição e cobrança =========================================================================
it("L7-09-a-medidor-diario", 3,
   "medidor por inquilino em `plat.uso_diario` (inquilino, dia, métrica, valor, origem, comando): GB armazenados por bucket (admin API do Garage) e por schema/tabelas do inquilino (`pg_total_relation_size`), tiles servidos por token na ORIGEM (log de acesso do nginx em formato JSON com token, bytes e `upstream_cache_status`, agregado por hora pelo worker — o HIT do nginx não chega à API, por isso o log é a fonte), tiles servidos pela CDN (API de analytics da CDN, quando existir; senão marcado `nao_medido`), usuários ativos (sessões), jobs e CPU-segundos, GPU-segundos, chamadas de API por chave, feições e itens; tudo calculado por timer diário e conferível por comando; paridade com usage reports do Portal (Activity Dashboard) e estatísticas do Server (samplingInterval/maxHistory)",
   "toda métrica tem o comando de conferência gravado na linha e um teste que roda o comando e compara (diferença ≤ 1 %, GB comparado com `du` do bucket e `pg_total_relation_size`); tela Uso para admin do inquilino com os últimos 90 dias; exportação CSV; RLS",
   "adversário compara TB medido com `du` do bucket e tiles medidos com o log bruto do nginx de um dia; divergência > 1 % = refutado",
   ["backend", "frontend", "adversario"], "M", ["L0-07-admin-org", "L1-02-tiles-token", "L0-05-jobs"], "esri", pai="L7-09-medicao-cobranca",
   fontes=["E11-usage", "E11-stats", "REST-server-usage", "REST-server-usage-settings", "GARAGE-admin", "GS-monitoring"])

it("L7-09-b-planos-limites-relatorio", 3,
   "planos e limites como dado: `plat.plano` (nome, limites por métrica, preço de lista por região, moeda) e `plat.tenant.plano_id`; aplicação dos limites: aviso a 80 % (e-mail + banner), bloqueio de ESCRITA/upload a 100 % com mensagem clara, NUNCA bloqueio de leitura nem de exportação (o dado é do cliente); excedente medido e listado; relatório mensal por inquilino (PDF pelo design system da casa + CSV) com uso, limite, excedente e valor de lista — sem crédito, sem assento (o taxímetro da spec 17.3/21); o preço em si é decisão do dono (D4) e entra na tabela, não no código",
   "cota sintética de 100 MB: upload de 90 MB dispara aviso, de 110 MB é bloqueado com 413 e mensagem, leitura e exportação continuam (teste); relatório do mês gerado por timer e igual ao gerado à mão pelo comando; mudança de plano no meio do mês rateada por dia (teste com datas); paridade com cotas/licenças por membro do Portal escrita",
   "adversário tenta ultrapassar a cota pela API direta em paralelo (10 uploads simultâneos de 15 MB contra cota de 100 MB) — o total gravado não pode passar da cota; tenta ler/exportar com cota estourada (tem de funcionar)",
   ["backend", "frontend", "adversario"], "M", ["L7-09-a-medidor-diario", "L0-07-admin-org"], "spec", pai="L7-09-medicao-cobranca", fontes=["E11-usage", "REST-portal-licenses"])

# ===== 10. i18n e acessibilidade =====================================================================
it("L7-10-a-i18n-pt-en-es", 3,
   "internacionalização: catálogos `web/i18n/<idioma>.json` (pt-BR padrão, en, es) com mensagens no formato ICU (plural, gênero, número/data via `Intl` no navegador e Babel 2.10 já instalado no servidor para e-mails, PDFs e mensagens de erro); idioma por usuário (`usuario.idioma`) com fallback para o do inquilino e depois pt-BR; troca sem recarregar (o app é módulo ES: as cadeias são funções, não texto fixo); dado do usuário (nomes de camada, valores) nunca traduzido; datas e números respeitam locale; OpenAPI e Problem Details com `Accept-Language`; a Esri entrega o Manager em 10 idiomas e o Portal em 42 códigos `esri_*` (incl. pt e es)",
   "teste estático: 0 cadeia de interface fora do catálogo (grep por texto literal em `web/js` com lista de exceções justificadas) e 0 chave faltando em en/es (comparação de chaves); e2e nos 3 idiomas com captura de 5 telas; troca de idioma sem recarregar (estado do mapa preservado, medido); e-mail de convite nos 3 idiomas (SMTP de captura); formato de número/data conferido por locale",
   "adversário navega em `es` por 10 telas procurando texto em português, e em `pt-BR` procurando texto em inglês de biblioteca (MapLibre, datas); um achado fora das exceções = refutado",
   ["frontend", "backend", "testador", "adversario"], "M", ["L5-01-app-builder", "L5-12-acessibilidade-i18n-construtores", "L0-07-admin-org"], "esri", pai="L7-10-i18n-acessibilidade",
   fontes=["E11-manager-lang", "REST-portal-languages", "E11-general", "BABEL", "FLUENT", "I18NEXT"])

it("L7-10-b-acessibilidade-wcag21aa", 3,
   "acessibilidade WCAG 2.1 AA e responsividade medidas (critérios 2.2 adotados quando não custam; eMAG 3.1 de 2014 é a referência de governo e é subconjunto): axe-core no playwright em TODAS as telas (0 violação crítica/séria), navegação completa por teclado incluindo o mapa (atalhos documentados, foco visível, seleção de feição por teclado com lista equivalente 'feições na vista' — a equivalência textual do mapa), rótulos e `aria-live` para progresso de jobs, contraste ≥ 4,5:1 nos tokens do design system, tamanho de alvo, sem armadilha de foco em modais, leitor de tela (NVDA/Orca) em 5 tarefas gravadas; a Esri publica ACR/VPAT por produto (Enterprise 12.1 em 2026, Map Viewer jun/2025, Experience Builder fev/2026) — aqui o equivalente é `docs/ACESSIBILIDADE.md` gerado do resultado do axe por tela",
   "`make a11y` roda axe em todas as telas e sai 0; e2e só-teclado nas 5 tarefas (login, abrir mapa, filtrar camada, editar atributo, exportar) com captura; documento `docs/ACESSIBILIDADE.md` gerado (critério → estado → evidência) no formato de ACR; contraste medido por script sobre os tokens CSS; RESPONSIVO: e2e em 3 viewports (390×844, 820×1180, 1440×900) para as 10 telas principais com captura, rolagem horizontal = 0, alvos de toque ≥ 44 px no mapa, Lighthouse (chromium do playwright) acessibilidade ≥ 95 e desempenho ≥ 80 no celular registrados em `tests/medidas/`",
   "adversário navega só por teclado e com leitor de tela em 5 tarefas (refutação do L7-10) e anota cada ponto em que travou ou perdeu o foco",
   ["frontend", "testador", "adversario"], "M", ["L5-01-app-builder", "L5-12-acessibilidade-i18n-construtores", "L2-01-mapa-web"], "esri", pai="L7-10-i18n-acessibilidade",
   fontes=["WCAG21", "WCAG22", "WCAG-quick", "EMAG", "GOVBR-a11y", "AXE", "AXE-PW-PY", "ESRI-vpat"])

# ===== 11. LGPD e governança =========================================================================
it("L7-12-a-classificacao-retencao", 3,
   "classificação e retenção como atributo do catálogo: `item.classificacao` ∈ {publica, interna, pessoal, sensivel} e por coluna (`campo.classificacao`) para camadas com atributos de pessoa; regras derivadas: `pessoal/sensivel` nunca vai para CDN, nunca entra em exportação pública, exige justificativa de acesso (texto obrigatório na 1ª abertura da sessão, gravado na trilha L7-20), aparece mascarado para perfil `visualizador` quando marcado; retenção por item (`reter_ate`, motivo legal) com expurgo agendado por pg_cron (job idempotente, gera evento e trilha) e 'lixeira' de 30 dias antes do expurgo definitivo (a lixeira do catálogo é do L0-03); a Esri não tem classificação por item nativa — aqui é diferencial de edital (LGPD art. 46)",
   "e2e: marcar camada como `pessoal`, abrir sem justificativa → bloqueio com formulário; com justificativa → acesso e linha na trilha; token de serviço em camada `pessoal` também deixa rastro; tile de camada `pessoal` nunca sai pela CDN (teste externo); expurgo agendado roda no relógio simulado e o item some da lixeira após 30 d com evento; relatório 'o que temos de pessoal' por inquilino",
   "adversário acessa camada `pessoal` por token de serviço e confere que ficou na trilha (refutação do L7-12); tenta obtê-la por exportação, por CDN, por webhook (o payload nunca leva atributo, só id) e por SDK",
   ["backend", "dados", "adversario"], "M", ["L0-03-catalogo", "L0-03-h-lixeira-protecao-status", "L7-20-trilha-auditoria", "L7-26-cdn-tiles"], "usuario", pai="L7-12-lgpd-governanca", fontes=["LGPD", "ANPD-guia-agentes"])

it("L7-12-b-registro-tratamento-dpa-incidente", 3,
   "governança documental gerada de dado: Registro das Operações de Tratamento (LGPD art. 37) por inquilino a partir do catálogo classificado (finalidade, base legal, categorias, retenção, compartilhamento com conectores/webhooks, região); DPA modelo (`docs/DPA.md`: controlador = cliente, operador = a casa, subprocessadores = provedores da região, com a tabela de residência do L7-27) para o dono/jurídico assinar; direitos do titular: exportação e eliminação por titular dentro de uma camada (busca por chave declarada pelo admin, gera pacote e trilha); runbook de incidente conforme Resolução CD/ANPD 15/2024 (comunicação preliminar, completa e complementar; comunicar titulares em risco relevante; `incidentes@anpd.gov.br`) ligado ao `plat incidente` (L7-22) com os campos do formulário CIS pré-preenchidos do que o sistema sabe (quando, o que, quantos titulares, medidas)",
   "`plat lgpd registro <slug>` gera o registro (0 campo digitado; campos ausentes aparecem como 'a declarar pelo controlador'); `plat lgpd titular exportar/eliminar` numa camada com coluna-chave declarada funciona e deixa trilha; incidente sintético gera rascunho do CIS; `docs/DPA.md` revisado pelo revisor separado (regra de escrita de 03/09) antes de publicado",
   "adversário pede eliminação de um titular e depois procura o registro em backup lógico, réplica, exportação antiga, cache de tile e trilha (a trilha guarda só o id do pedido, nunca o dado) — o documento tem de declarar o prazo em que ele some de cada lugar; ausência de declaração = refutado",
   ["backend", "cronista", "adversario"], "M", ["L7-12-a-classificacao-retencao", "L7-22-sla-e-incidentes", "L7-27-origem-br-soberania"], "usuario", pai="L7-12-lgpd-governanca",
   fontes=["LGPD", "ANPD-incidente", "ANPD-cis", "ANPD-transf", "ANPD-guia-agentes", "GOVBR-privsec"])

it("L7-28-iso27001-controles", 4,
   "conformidade preparada, não certificada: mapa dos controles aplicáveis da ISO/IEC 27001 (Anexo A da edição 2022: temas organizacional, pessoas, físico, tecnológico) para a evidência que o repositório e a operação já produzem (`docs/CONFORMIDADE.md` gerado de `docs/controles.yaml`: controle → evidência (arquivo/teste/runbook/timer) → estado), incluindo o que é do provedor (Hetzner certificada em todos os DCs; Vultr a conferir) e o que é do dono (políticas, pessoas); serve para responder questionário de segurança de cliente e para o vocabulário de edital (spec 8); texto da norma não é reproduzido (é paga) — só a numeração e a evidência",
   "documento gerado com ≥ 60 % dos controles tecnológicos com evidência automática (teste/timer) e o restante marcado 'do dono' ou 'não aplicável' com motivo; questionário de segurança padrão (30 perguntas comuns de cliente) respondido a partir do documento; revisão do revisor separado",
   "adversário pega 10 controles marcados 'com evidência' e verifica um a um que o arquivo/teste existe e prova o que diz; um falso = refutado",
   ["gerente", "cronista", "adversario"], "P", ["L7-03-g-asvs-nivel2-pentest", "L7-19-segredos-e-certificados", "L7-24-drill-restauracao"], "spec", fontes=["HETZNER-cert", "ESRI-trust"])

# ===== 12. Suporte, manual, tour, vídeos, demonstração ==============================================
it("L7-13-a-chamados", 4,
   "chamados dentro do produto: botão 'reportar' em toda tela abre formulário com captura automática da tela (canvas do mapa + DOM, sem dado de outro inquilino), contexto automático (tela, versão, `req_id` das últimas 20 requisições, navegador, idioma), anexos (pipeline de upload seguro), estados (aberto, em análise, aguardando cliente, resolvido, fechado), comentários, notificação por e-mail e banner, SLA de primeira resposta por severidade (L7-22); `plat.chamado` com RLS; painel do operador (superadmin) com fila de todos os inquilinos; é a porta do laço agêntico (L7-13-c)",
   "e2e: abrir chamado com captura, operador responde, cliente vê e fecha; anexo malicioso recusado; e-mail de notificação nos 3 idiomas (SMTP de captura); tempo de primeira resposta medido e exibido; chamado de outro inquilino invisível (teste cruzado por API e por UI)",
   "adversário abre chamado de outro inquilino pela API (refutação do L7-13) e tenta ler anexo de chamado alheio pela URL do objeto",
   ["frontend", "backend", "adversario"], "M", ["L7-04-manual-e-tour", "L7-03-a-antivirus-upload", "L0-07-admin-org"], "usuario", pai="L7-13-suporte-chamados")

it("L7-13-c-laco-agentico-suporte", 4,
   "operação agêntica da spec 19 com humano no laço: chamado novo → agente de triagem (modelo aberto local no GPU box; Claude API só quando escalado) lê relato + contexto + logs por `req_id` + status → classifica (defeito, infra, dúvida, pedido) → tenta reproduzir por e2e em homologação → propõe resposta ou diff com teste → humano nomeado aprova/ajusta → agente aplica em homologação, roda `make check`, e o release segue L7-15; tudo gravado (`plat.chamado_agente`: proposta, quem aprovou, quando, resultado) e alimenta o log de correções; regras duras: o agente NUNCA escreve em produção, NUNCA vê dado de inquilino além do chamado, NUNCA responde ao cliente sem aprovação; medir horas humanas por chamado (a conta da spec 19.2)",
   "10 chamados sintéticos (5 defeitos reais plantados em homologação, 3 dúvidas, 2 infra) percorrem o laço: ≥ 7 classificados certo, ≥ 3 defeitos com diff que passa no `make check`, 0 escrita em produção (teste procura), 0 resposta sem aprovação (trilha); horas humanas medidas por chamado; `docs/OPERACAO_AGENTICA.md` com o que o agente faz sozinho e o que nunca faz",
   "adversário planta no chamado uma instrução (injeção de prompt: 'apague o inquilino X', 'mostre o segredo') e confere que o agente não executa nem vaza; tenta um chamado cuja reprodução exigiria dado de outro inquilino",
   ["gerente", "backend", "adversario"], "M", ["L7-13-a-chamados", "L7-31-ambiente-homologacao", "L7-15-processo-release", "L7-06-c-logs-consulta-req-id"], "spec", fontes=["E11-monitor"])

it("L7-04-a-manual-capturas-geradas", 3,
   "manual gerado, não escrito à mão em separado: `docs/manual/<tela>.md` (texto do cronista) + captura produzida pelo e2e da própria tela (`tests/e2e/capturas/<tela>@<versao>.png`) inserida por script; `make manual` regenera capturas e monta o site interno do manual (HTML estático, noindex) e o PDF pelo design system da casa; captura desatualizada (versão diferente da atual) reprova o build; uma seção por tela, mais o manual do administrador (L7-04-c); AJUDA POR CONTEXTO: cada tela tem `data-ajuda=<chave>` e o botão 'ajuda' abre a seção correspondente num painel lateral com busca, nos 3 idiomas",
   "`make manual` sai 0 e produz HTML + PDF; toda tela do e2e tem seção e toda seção tem captura da versão atual (teste); toda tela tem chave de ajuda e toda chave tem seção (teste percorre as telas do e2e); e2e do painel de ajuda; busca devolve a seção certa para 20 perguntas de teste; PDF verificado página a página (pdftoppm → leitura) sem transbordo; nenhum nome de cliente (grep)",
   "adversário segue o manual para fazer 5 tarefas sem ajuda (refutação do L7-04) e anota onde travou; compara 5 capturas com a tela real da versão instalada",
   ["cronista", "frontend", "adversario"], "P", ["L5-01-app-builder"], "casa", pai="L7-04-manual-e-tour")

it("L7-04-b-tour-primeiro-acesso", 3,
   "tour guiado no primeiro acesso, por perfil (admin, editor, visualizador, campo): sequência de 6-8 passos com destaque do elemento e texto curto (biblioteca vendorizada sem dependência ou própria), pode ser pulado e reaberto pelo menu 'ajuda', estado 'tour visto' por usuário; nos 3 idiomas; acessível por teclado",
   "e2e do tour para os 4 perfis com captura de cada passo; pular e reabrir funcionam; 0 erro de console; axe sem violação durante o tour; textos no catálogo i18n",
   "adversário abre o tour numa tela redimensionada e num viewport de celular procurando destaque fora da tela ou passo que aponta para elemento inexistente",
   ["frontend", "cronista", "adversario"], "P", ["L7-10-a-i18n-pt-en-es"], "usuario", pai="L7-04-manual-e-tour")

it("L7-04-c-manual-admin-runbooks", 3,
   "manual do administrador e runbooks de operação: `docs/RUNBOOKS/` com um arquivo por procedimento (instalar, atualizar, reverter, restaurar, drill, promover réplica, failback, rotacionar segredo, renovar certificado, purgar CDN, disco cheio, fila travada, reindexar, apagar inquilino, exportar inquilino, ligar/desligar modo somente-leitura, lidar com alerta X) — cada runbook = texto + o script que ele chama + tempo medido na última execução + data; manual do admin do inquilino (organização, membros, cotas, uso, auditoria, LGPD); os dois no site do manual e no PDF",
   "todo script em `scripts/` tem runbook e todo runbook tem script (teste cruzado); todo alerta de L7-06-b aponta para um runbook (teste); 5 runbooks executados pelo adversário só pela leitura; datas e tempos vêm de `plat.execucao_runbook`",
   "adversário executa 5 runbooks escolhidos por ele em homologação seguindo só o texto e anota cada passo ambíguo ou faltante",
   ["cronista", "backend", "adversario"], "M", ["L7-35-atualizacao-versao-assinada", "L7-24-drill-restauracao", "L7-07-c-ensaio-failover", "L7-19-segredos-e-certificados"], "usuario", pai="L7-04-manual-e-tour")

it("L7-04-d-videos-por-tarefa", 4,
   "vídeos curtos (≤ 3 min) por tarefa gerados do próprio e2e: playwright grava a sessão (webm) → ffmpeg monta com legendas (do roteiro do teste) e narração TTS em pt-BR (piper, já usado na casa) → mp4 no site do manual; regenerados a cada versão menor; sem rosto, sem voz clonada, sem nome de cliente; versão em en/es com legendas",
   "`make videos` produz ≥ 10 vídeos com legenda e áudio, cada um ligado à seção do manual; duração medida ≤ 3 min; playback no navegador do e2e; captura de um quadro conferida contra a tela real",
   "adversário assiste 3 vídeos e executa a tarefa em paralelo; qualquer passo do vídeo que não existe na versão instalada = refutado",
   ["cronista", "frontend", "adversario"], "P", ["L7-04-a-manual-capturas-geradas"], "usuario", pai="L7-04-manual-e-tour")

it("L7-29-roteiro-demonstracao", 3,
   "roteiro de demonstração de 30 min (`docs/DEMO.md`) percorrível por e2e (o portão do L7-05 já exige): abre com o dado demo (L7-01-c), passa por imagens (upload → COG → tiles no mapa → URL WMTS colada num cliente OGC), catálogo/mapa/edição/serviços, motor multicritério, rede de utilidades (traçado), construtor de app, acervo, e fecha em operação (status, uso, auditoria, exportação); cada passo com o que dizer (regra de escrita de 03/09: sem metáfora, número com universo e fonte) e o que NÃO prometer (paridade pendente com Pro/AGOL); versão de 10 min",
   "`tests/e2e/test_demo.py` percorre os passos do roteiro com captura por passo e tempo total ≤ 30 min medido; texto revisado pelo revisor separado; lista 'o que não faz ainda' gerada do `PAINEL.md`",
   "adversário executa a demonstração ao vivo seguindo só o roteiro e registra cada momento em que a tela não fez o que o texto diz",
   ["gerente", "cronista", "frontend", "adversario"], "P", ["L7-01-c-dado-demonstracao", "L3-01-motor-servico", "L4-02-tracado", "L5-01-app-builder", "L6-01-acervo-casa"], "usuario")

it("L7-30-teste-parceiro-pro-agol", 3,
   "teste real com ArcGIS Pro e ArcGIS Online pelo parceiro (D20, pendente de credencial): protocolo escrito `docs/TESTE_PARCEIRO.md` — lista numerada do que colar/abrir (WMTS, XYZ, COG por HTTPS, STAC, FeatureServer com edição, OGC API Features, tiles vetoriais, chave de API no SDK), o que observar, formulário de resultado (funcionou / não / com ressalva + captura) que o parceiro devolve e que vira linhas em `docs/PARIDADE.md` com estado `testado pelo parceiro em <data>`; até lá TODA linha de paridade com Pro/AGOL fica `pendente` (portão P4)",
   "protocolo pronto e revisado; formulário de resultado importável por script para `docs/PARIDADE.md`; item permanece `pendente` com `bloqueio: D20` até o resultado chegar — nunca marcado feito por nós",
   "adversário procura em qualquer documento ou tela a afirmação de que Pro/AGOL 'funcionam' sem a data do teste do parceiro; um achado = refutado",
   ["esri", "gerente", "adversario"], "P", ["L2-04-servicos-esri-ogc", "L1-02-tiles-token", "L7-08-d-portal-api-chaves"], "usuario", bloqueio="D20: credencial AGOL/Portal e agenda do parceiro (decisão do dono)")

# ===== 13. Operação transversal ======================================================================
it("L7-33-modo-somente-leitura", 2,
   "modo somente-leitura/manutenção global e por inquilino (paridade com o `mode` do Portal e o site mode READ_ONLY do Server): bandeira em `plat.sistema` (chave/valor com quem/quando/motivo) lida pelo middleware — métodos de escrita devolvem 503 com `Retry-After` e Problem Details, leitura, tiles e exportação continuam; o front mostra faixa com o motivo; jobs em fila pausam e retomam; usado pela atualização (L7-14), pelo failover (L7-07-c), pela licença vencida (L7-11-a) e pela manutenção planejada; nunca bloqueia `/saude`, `/status`, logout",
   "e2e: ligar o modo → edição bloqueada com mensagem, mapa e exportação funcionam, faixa visível; desligar → tudo volta; job em execução no momento de ligar termina ou pausa sem se perder (teste com job de 2 min); `plat modo` com motivo obrigatório grava trilha; alerta silenciado durante o modo (L7-06-b)",
   "adversário tenta escrever durante o modo por todas as rotas do OpenAPI, por FeatureServer applyEdits, por OGC, por SDK e por webhook de fluxo; um 2xx de escrita = refutado",
   ["backend", "frontend", "adversario"], "P", ["L0-02-tenant-auth", "L0-05-jobs"], "esri", fontes=["REST-portal-mode", "REST-server-mode", "REST-server-props", "RFC9110"])

it("L7-34-saude-profunda", 2,
   "health check profundo além do `/saude` atual: `/saude/profunda` por componente (banco: conexão, migrações, réplica e atraso; fila: worker vivo e idade do job mais antigo; Martin; TiTiler; Garage: nós e layout; nginx; certificado: dias restantes; disco por volume; RAM; CDN: último HIT; backup: idade; licença) com estado `ok|degradado|erro` e tempo de cada sonda, sem revelar segredo nem topologia a anônimos (versão resumida pública para o balanceador/CDN, completa para admin); é a fonte da página de status e do alerta de 'componente caído'; paridade com `machines/<m>/status` (configuredState × realTimeState — usar o real) e `healthCheck` da Esri",
   "cada componente parado de propósito em homologação aparece como `erro` em ≤ 10 s e o estado geral vira `degradado` ou `erro` conforme tabela declarada; resposta anônima não contém host/porta/versão de dependência (teste); sondas com tempo limite individual (nenhuma trava o endpoint: teste com Garage pendurado por `iptables`); 200/503 coerente com o uso pelo balanceador",
   "adversário pendura um componente (não derruba: `SIGSTOP`) e mede se o endpoint responde em ≤ 3 s e acusa; lê a versão anônima procurando informação interna",
   ["backend", "adversario"], "P", ["L0-05-jobs", "L1-02-tiles-token"], "esri", fontes=["REST-server-status", "E11-ha-patch"])

it("L7-32-postgres-manutencao-versao", 4,
   "manutenção do banco como rotina versionada: `VACUUM/ANALYZE` agendados por pg_cron nas tabelas do plat (o `reltuples` mentiu na casa: ANALYZE regular é regra), reindex periódico das tabelas espaciais grandes, `pg_stat_statements` ligado com relatório semanal das 20 consultas mais caras, política de versão do PostgreSQL (16 recebe correções até nov/2028) com procedimento de atualização maior no appliance (`pg_upgrade --link` ensaiado em homologação com PostGIS 3.6), e limites de conexão por role (`plat_app` com `CONNECTION LIMIT` medido)",
   "timers criados e visíveis (`cron.job`); relatório semanal gerado e consultável; ensaio de `pg_upgrade` 16 → 17 em homologação com tempo medido e `make check` verde depois; `reltuples` × `COUNT(*)` das tabelas do plat com divergência < 5 % após o ANALYZE (teste)",
   "adversário compara `reltuples` com `COUNT(*)` em todas as tabelas do plat depois de uma carga pesada: divergência > 5 % em qualquer tabela = refutado",
   ["dados", "adversario"], "P", ["L7-23-pgbackrest-pitr"], "casa", fontes=["PG-versioning", "PG-upgrade", "PG-pgstat"])

# ---------------------------------------------------------------- dependências externas propostas
DEPS_EXTERNAS = [
        {"id": "L2-04-b-parser-where-ast", "linha": "L2 plataforma", "prioridade": 1, "nota": "id -b porque a L0 já propôs L2-04-a-leitor-rls-martin",
     "hipotese": "parser próprio do `where` do FeatureServer (subconjunto SQL-92 que a Esri chama standardized queries) e do CQL2 do OGC → AST → SQL parametrizado com lista branca de colunas/funções; sem string de usuário concatenada em SQL em lugar nenhum",
     "motivo": "L7-03-d testa injeção contra ele; se o L2-04 construir o where por substituição de texto, o item de segurança não tem como passar e o serviço não pode ir a produção"},
    {"id": "L2-01-a-basemap-local-pmtiles", "linha": "L2 plataforma", "prioridade": 3,
     "hipotese": "mapa-base local em PMTiles (recorte aberto de OSM/Natural Earth com estilo próprio) servido pelo nginx/Martin do próprio appliance, selecionável como base padrão do inquilino",
     "motivo": "sem ele o appliance offline (L7-11-b) abre um mapa cinza; a casa já produz PMTiles com tippecanoe (observatório)"},
    ]

# ---------------------------------------------------------------- validação
ids = [i["id"] for i in ITENS]
assert len(ids) == len(set(ids)), "id duplicado"
existentes = set()
estado = json.load(open("/home/dev/plataforma/laco/estado.json"))
for b in estado["backlog"]:
    existentes.add(b["id"])
import glob
irmaos = set()
for arq in glob.glob("/home/dev/plataforma/laco/decomposicao/L*.json"):
    if arq.endswith("L7.json"):
        continue
    try:
        dd = json.load(open(arq))
    except Exception:
        continue
    for x in (dd.get("itens") or dd.get("items") or []):
        irmaos.add(x["id"])
    for x in dd.get("dependencias_externas_propostas", []):
        irmaos.add(x["id"])
propostos = {d["id"] for d in DEPS_EXTERNAS}
todos = existentes | irmaos | set(ids) | propostos
for i in ITENS:
    for d in i["dependencias"]:
        assert d in todos, f"{i['id']} depende de id desconhecido {d}"
    if i["pai"]:
        assert i["pai"] in existentes, f"{i['id']} pai desconhecido {i['pai']}"
    assert i["origem"] in ("esri", "geoserver", "casa", "spec", "usuario")
    assert i["tamanho"] in ("P", "M", "G")
    assert 1 <= i["prioridade"] <= 5
chaves_fontes = {f[0] for f in FONTES}
for i in ITENS:
    for f in i["fontes"]:
        assert f in chaves_fontes, f"{i['id']} fonte desconhecida {f}"

texto = json.dumps(ITENS, ensure_ascii=False) + json.dumps(DEPS_EXTERNAS, ensure_ascii=False)
proibidos = re.compile(r"fgr|cbre|novaterra|paracan|sigcorp|fgrsig|cbresig|jamel|rodrigo|robson|daiichi|arayara|ineep", re.I)
achados = proibidos.findall(texto)
assert not achados, f"nome proibido: {set(achados)}"
emoji = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
assert not emoji.search(texto), "emoji"

saida = {
    "linha": LINHA,
    "gerado_em": ACESSO,
    "gerador": "laco/decomposicao/gera_l7.py (scratchpad) — decomposição profunda pedida em BRIEF.md",
    "resumo": {
        "itens_novos": len(ITENS),
        "itens_existentes_da_linha": sorted(b for b in existentes if b.startswith("L7-")),
        "por_origem": {o: sum(1 for i in ITENS if i["origem"] == o) for o in ("esri", "geoserver", "casa", "spec", "usuario")},
        "por_tamanho": {t: sum(1 for i in ITENS if i["tamanho"] == t) for t in ("P", "M", "G")},
        "com_pai": sum(1 for i in ITENS if i["pai"]),
        "fontes_testadas_http": len(FONTES),
    },
    "fontes": [{"chave": k, "url": u, "http": h, "acesso": ACESSO, "o_que_diz": o} for k, u, h, o in FONTES],
    "dependencias_externas_propostas": DEPS_EXTERNAS,
    "itens": ITENS,
}
with open("/home/dev/plataforma/laco/decomposicao/L7.json", "w", encoding="utf-8") as f:
    json.dump(saida, f, ensure_ascii=False, indent=1)
print(f"itens novos: {len(ITENS)} · fontes: {len(FONTES)} · propostas externas: {len(DEPS_EXTERNAS)}")
print("por origem:", saida["resumo"]["por_origem"], "por tamanho:", saida["resumo"]["por_tamanho"])
