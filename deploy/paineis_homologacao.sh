#!/usr/bin/env bash
# Homologação dos painéis do item L7-06-d-paineis.
#
# Sobe uma pilha de observação PRÓPRIA (Prometheus, postgres_exporter e Grafana em portas de
# homologação, dados em diretório temporário — nunca os da casa em /opt/monitoring) que lê a MESMA
# `deploy/grafana/provisioning` e os MESMOS `deploy/grafana/paineis/*.json` de produção. Do
# provisionamento só se troca o ENDEREÇO do Prometheus na fonte de dado e o schema nas consultas do
# postgres_exporter — o resto (uid da fonte, uid de cada painel, cada consulta PromQL) é letra por
# letra o que vai para produção.
#
#   bash deploy/paineis_homologacao.sh subir      # sobe tudo, gera carga curta e fica no ar
#   bash deploy/paineis_homologacao.sh derrubar   # mata pelo PID e apaga o diretório de trabalho
#
# `subir` escreve um arquivo de ambiente com as portas; os testes o leem:
#   set -a; source /tmp/plat_paineis_homolog/ambiente; set +a
#   bash /home/dev/plataforma/laco/roda_teste.sh tests/e2e/test_paineis.py -q
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TRAB="${PLAT_PAINEIS_TRAB:-/tmp/plat_paineis_homolog}"
PORTA_PROM="${PORTA_PROM:-8314}"
PORTA_GRAFANA="${PORTA_GRAFANA:-8315}"
PORTA_PGEXP="${PORTA_PGEXP:-8317}"
API="${PLAT_API_URL:-http://127.0.0.1:8307}"
NOME_GRAFANA="plat-paineis-homolog"
IMAGEM_GRAFANA="${IMAGEM_GRAFANA:-grafana/grafana:11.2.0}"

derrubar() {
  docker rm -f "$NOME_GRAFANA" >/dev/null 2>&1
  for arq in "$TRAB"/*.pid; do
    [ -f "$arq" ] || continue
    kill "$(cat "$arq")" 2>/dev/null
  done
  sleep 1
  if [ -f "$TRAB/papel_metrica" ]; then
    papel="$(sed -n 1p "$TRAB/papel_metrica")"; schema="$(sed -n 2p "$TRAB/papel_metrica")"
    sudo -u postgres psql -d iagro_sat -tAc \
      "REVOKE ALL ON ALL TABLES IN SCHEMA $schema FROM $papel; REVOKE ALL ON SCHEMA $schema FROM $papel" \
      >/dev/null 2>&1
  fi
  rm -rf "$TRAB"
  echo "derrubado"
}

case "${1:-subir}" in
  derrubar) derrubar; exit 0 ;;
  subir) ;;
  *) echo "uso: paineis_homologacao.sh [subir|derrubar]"; exit 2 ;;
esac

derrubar >/dev/null 2>&1
mkdir -p "$TRAB/prom" "$TRAB/provisioning/datasources" "$TRAB/provisioning/dashboards"

curl -sf --max-time 5 "$API/metrics" >/dev/null || {
  echo "ERRO: $API/metrics não responde. Suba a API da trilha antes (uvicorn na porta da trilha)."
  exit 2
}

# ---------------------------------------------------------------- postgres_exporter da trilha
# O exporter de produção lê o schema `plat`; esta cópia lê o schema DA TRILHA, que é onde a carga
# curta acontece. A troca é textual e só no nome do schema: as consultas continuam as mesmas.
SCHEMA="${PLAT_SCHEMA:-plat}"
sed "s/\bplat\./${SCHEMA}./g; s/= 'plat'/= '${SCHEMA}'/g" \
  "$RAIZ/deploy/postgres_exporter_queries.yaml" > "$TRAB/consultas.yaml"
# Papel de métrica: reusa o `plat_metrica_pg` de PRODUÇÃO (item L7-06-a) em vez de criar um papel só
# para a homologação. Dois motivos medidos em 07/09/2026: (a) papel novo precisa de linha em
# `pg_hba.conf` além do GRANT — sem ela o exporter sobe e só falha na 1ª consulta ("no pg_hba.conf
# entry"), e editar o pg_hba de um cluster compartilhado por dezenas de frentes por causa de uma
# homologação é caro demais; (b) o que se quer provar é justamente que o painel funciona com o papel
# que produção usa (pg_monitor: é ele que libera pg_ls_waldir e pg_stat_replication, sem os quais o
# painel do banco fica sem WAL e sem réplica). Os GRANT abaixo dão a ele leitura do schema DA TRILHA
# enquanto a homologação dura; `derrubar` os retira.
PAPEL_METRICA="plat_metrica_pg"
DSN_PGEXP="$(sudo sed -n 's/^DATA_SOURCE_NAME="\(.*\)"$/\1/p' /etc/default/prometheus-postgres-exporter)"
if [ -n "$DSN_PGEXP" ]; then
  sudo -u postgres psql -d iagro_sat -v ON_ERROR_STOP=1 >"$TRAB/papel.log" 2>&1 <<SQL
GRANT USAGE ON SCHEMA ${SCHEMA} TO ${PAPEL_METRICA};
GRANT SELECT ON ALL TABLES IN SCHEMA ${SCHEMA} TO ${PAPEL_METRICA};
SQL
  [ $? -eq 0 ] || echo "AVISO: GRANT de leitura da trilha ao papel de métrica falhou (ver $TRAB/papel.log)"
  printf '%s\n%s\n' "$PAPEL_METRICA" "$SCHEMA" > "$TRAB/papel_metrica"
else
  echo "AVISO: /etc/default/prometheus-postgres-exporter sem DATA_SOURCE_NAME"
fi
if [ -z "$DSN_PGEXP" ]; then
  # sem DSN próprio de métrica na trilha, usa o mesmo usuário do aplicativo (só leitura das consultas)
  DSN_PGEXP="$(grep -m1 '^PLAT_DSN=' "${PLAT_ENV_ARQUIVO:-/dev/null}" 2>/dev/null | cut -d= -f2-)"
fi
[ -n "$DSN_PGEXP" ] || DSN_PGEXP="${PLAT_DSN:-}"
if [ -n "$DSN_PGEXP" ]; then
  DATA_SOURCE_NAME="$DSN_PGEXP" nohup /usr/bin/prometheus-postgres-exporter \
    --web.listen-address="127.0.0.1:$PORTA_PGEXP" \
    --extend.query-path="$TRAB/consultas.yaml" \
    --no-collector.stat_user_tables --no-collector.statio_user_tables \
    >"$TRAB/pgexp.log" 2>&1 &
  echo $! > "$TRAB/pgexp.pid"
else
  echo "AVISO: sem PLAT_DSN no ambiente — o painel do banco vai medir o exporter da casa (schema plat)"
  PORTA_PGEXP=9187
fi

# ---------------------------------------------------------------- servidor de ladrilho de homologação
# O `plat-martin` da casa serve as camadas de inquilinos reais; nesta máquina, em 07/09/2026, as funções
# de tile de `d_demo` apontam para o schema de uma trilha que já foi apagada (`plat_tmapa`), então TODA
# fonte devolve 500 e o Martin nem chega a consultar o cache. Isso é achado do ambiente, não do item —
# mas deixaria dois quadros do painel sem dado por motivo alheio ao que se quer medir. A homologação sobe
# um Martin PRÓPRIO sobre uma fonte de ladrilho criada aqui, no schema de trabalho DA TRILHA (some junto
# com ela), e os quadros passam a medir o que dizem medir: taxa de ladrilho e acerto de cache.
PORTA_MARTIN="${PORTA_MARTIN:-8318}"
# papel do aplicativo lido do próprio DSN da trilha (postgresql://<papel>:...): nada digitado à mão
PAPEL_APP="$(printf '%s' "${PLAT_DSN:-postgresql://plat_app}" | sed -E 's#^[^/]*//([^:@/]+).*#\1#')"
SCHEMA_TRAB="${PLAT_SCHEMA_TRABALHO:-plat_trabalho}"
sudo -u postgres psql -d iagro_sat -v ON_ERROR_STOP=1 >"$TRAB/fonte.log" 2>&1 <<SQL
CREATE TABLE IF NOT EXISTS ${SCHEMA_TRAB}.ladrilho_homologacao (
  id bigserial PRIMARY KEY, geom geometry(Polygon, 4326));
TRUNCATE ${SCHEMA_TRAB}.ladrilho_homologacao;
INSERT INTO ${SCHEMA_TRAB}.ladrilho_homologacao (geom)
SELECT (ST_HexagonGrid(0.25, ST_MakeEnvelope(-54, -34, -34, -5, 4326))).geom;
CREATE INDEX IF NOT EXISTS ix_ladrilho_homologacao_geom
  ON ${SCHEMA_TRAB}.ladrilho_homologacao USING gist (geom);
ANALYZE ${SCHEMA_TRAB}.ladrilho_homologacao;
-- a tabela nasce do superusuário; sem este GRANT o Martin (papel do aplicativo) não a enxerga
GRANT SELECT ON ${SCHEMA_TRAB}.ladrilho_homologacao TO ${PAPEL_APP};
SQL
if [ $? -ne 0 ]; then echo "AVISO: fonte de ladrilho de homologação não pôde ser criada (ver $TRAB/fonte.log)"; fi
cat > "$TRAB/martin.yaml" <<YML
listen_addresses: '127.0.0.1:$PORTA_MARTIN'
worker_processes: 1
postgres:
  connection_string: \${PLAT_DSN_HOMOLOG}
  auto_publish:
    from_schemas: ${SCHEMA_TRAB}
    tables: true
    functions: false
  pool_size: 2
  default_srid: 4326
cache:
  size_mb: 16
  expiry: 5m
YML
PLAT_DSN_HOMOLOG="${PLAT_DSN}" nohup /usr/local/bin/martin --config "$TRAB/martin.yaml" \
  >"$TRAB/martin.log" 2>&1 &
echo $! > "$TRAB/martin.pid"

# ---------------------------------------------------------------- Prometheus de homologação
# Os NOMES DE JOB são os mesmos de produção (`plat-api`, `plat-garage`, ...): painel que filtra por
# job continua valendo nos dois lugares.
cat > "$TRAB/prometheus.yml" <<YML
global:
  scrape_interval: 10s
  evaluation_interval: 10s
scrape_configs:
  - job_name: plat-api
    static_configs: [{targets: ['${API#http://}']}]
  - job_name: plat-worker
    static_configs: [{targets: ['127.0.0.1:${PLAT_WORKER_PORTA:-8316}']}]
  - job_name: plat-martin
    metrics_path: /_/metrics
    static_configs: [{targets: ['127.0.0.1:$PORTA_MARTIN']}]
  - job_name: plat-postgres-exporter
    static_configs: [{targets: ['127.0.0.1:$PORTA_PGEXP']}]
  - job_name: plat-nginx-exporter
    static_configs: [{targets: ['127.0.0.1:9113']}]
  - job_name: plat-garage
    static_configs: [{targets: ['127.0.0.1:3903']}]
  - job_name: node-exporter
    static_configs: [{targets: ['127.0.0.1:9100']}]
YML
promtool check config "$TRAB/prometheus.yml" >/dev/null || { echo "ERRO: prometheus.yml inválido"; exit 3; }
nohup prometheus --config.file="$TRAB/prometheus.yml" --storage.tsdb.path="$TRAB/prom" \
  --web.listen-address="127.0.0.1:$PORTA_PROM" --storage.tsdb.retention.time=2h \
  >"$TRAB/prom.log" 2>&1 &
echo $! > "$TRAB/prom.pid"

# ---------------------------------------------------------------- Grafana de homologação
sed "s#http://127.0.0.1:9090#http://127.0.0.1:$PORTA_PROM#" \
  "$RAIZ/deploy/grafana/provisioning/datasources/plat-prometheus.yml" \
  > "$TRAB/provisioning/datasources/plat-prometheus.yml"
cp "$RAIZ/deploy/grafana/provisioning/dashboards/plat.yml" "$TRAB/provisioning/dashboards/plat.yml"
# CÓPIA dos painéis, não o diretório do repositório: a refutação do item precisa tirar e repor um
# arquivo para ver o provisionador reagir, e isso não pode mexer no que está versionado.
mkdir -p "$TRAB/paineis"
cp "$RAIZ"/deploy/grafana/paineis/*.json "$TRAB/paineis/"
SENHA_GRAFANA="homolog-$(openssl rand -hex 8)"
printf '%s' "$SENHA_GRAFANA" > "$TRAB/senha_grafana"
docker run -d --rm --name "$NOME_GRAFANA" --network host \
  -e GF_SERVER_HTTP_ADDR=127.0.0.1 -e GF_SERVER_HTTP_PORT="$PORTA_GRAFANA" \
  -e GF_SECURITY_ADMIN_USER=admin -e GF_SECURITY_ADMIN_PASSWORD="$SENHA_GRAFANA" \
  -e GF_USERS_ALLOW_SIGN_UP=false -e GF_ANALYTICS_REPORTING_ENABLED=false \
  -e GF_ANALYTICS_CHECK_FOR_UPDATES=false -e GF_NEWS_NEWS_FEED_ENABLED=false \
  -v "$TRAB/provisioning:/etc/grafana/provisioning:ro" \
  -v "$TRAB/paineis:/var/lib/grafana/dashboards/plat:ro" \
  "$IMAGEM_GRAFANA" >/dev/null || { echo "ERRO: docker run do Grafana falhou"; exit 3; }

for _ in $(seq 90); do
  curl -sf --max-time 2 "http://127.0.0.1:$PORTA_PROM/-/ready" >/dev/null &&
  curl -sf --max-time 2 "http://127.0.0.1:$PORTA_GRAFANA/api/health" >/dev/null && break
  sleep 1
done

cat > "$TRAB/ambiente" <<AMB
PLAT_PAINEIS_PROM=http://127.0.0.1:$PORTA_PROM
PLAT_PAINEIS_GRAFANA=http://127.0.0.1:$PORTA_GRAFANA
PLAT_PAINEIS_GRAFANA_SENHA=$SENHA_GRAFANA
PLAT_PAINEIS_TRAB=$TRAB
PLAT_PAINEIS_ARQUIVOS=$TRAB/paineis
AMB

# ---------------------------------------------------------------- carga curta
PLAT_MARTIN_URL="http://127.0.0.1:$PORTA_MARTIN" \
  "$RAIZ/venv/bin/python" "$RAIZ/deploy/paineis_carga.py" "$API" "$TRAB/carga.json" || {
  echo "ERRO: a carga curta falhou"; exit 4; }

# tempo de duas raspagens depois da carga, para toda família nova ter ao menos 2 amostras (rate())
sleep 35
echo "no ar: prometheus $PORTA_PROM, grafana $PORTA_GRAFANA, postgres_exporter $PORTA_PGEXP, martin $PORTA_MARTIN"
echo "ambiente em $TRAB/ambiente"
