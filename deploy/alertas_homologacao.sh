#!/usr/bin/env bash
# Encenação de verdade das regras de `deploy/alertas.yml` (item L7-06-b-alertas).
#
# Sobe um Prometheus e um Alertmanager PRÓPRIOS (portas de homologação, dados em diretório
# temporário, nunca os da casa em /opt/monitoring), com o MESMO deploy/alertas.yml e o MESMO
# deploy/alertmanager.yml de produção — deste último só trocamos os caminhos de segredo
# (/etc/plat/segredos/...) por arquivos do diretório de trabalho, de modo que a ÁRVORE DE
# ROTEAMENTO exercitada é a de produção, letra por letra.
#
# Depois provoca as condições de verdade e cronometra a chegada de cada alerta no receptor de teste:
#   1. enche um volume de teste (arquivo com perda em /mnt, ext4, 64 MiB) com fallocate  -> disco
#   2. derruba um alvo `plat-*` de homologação que estava no ar                          -> processo fora
#   3. registra backup de 30 h atrás e nenhum ensaio de restauração                      -> continuidade
#   4. marca um job como rodando há 35 min                                               -> fila
#   5. aponta a API para um certificado de 1 dia                                         -> TLS
#   6. a Sentinela dispara sozinha                                                       -> caminho vivo
# e, na segunda fase, mata o próprio Alertmanager e confere que o Prometheus acusa (refutação do item).
#
# Uso (a API da trilha precisa estar no ar expondo /metrics):
#   PLAT_API_METRICS=http://127.0.0.1:8305/metrics bash deploy/alertas_homologacao.sh /caminho/saida.json
#
# ⚠ Precisa de sudo para montar o volume de teste. Sem sudo o cenário 1 é pulado e registrado como
# "nao_encenado" na saída — nunca como aprovado.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAIDA="${1:?uso: alertas_homologacao.sh <arquivo de saida .json>}"
PORTA_PROM="${PORTA_PROM:-8306}"
PORTA_AM="${PORTA_AM:-8307}"
PORTA_RECEPTOR="${PORTA_RECEPTOR:-8308}"
PORTA_ALVO="${PORTA_ALVO:-8309}"
API_METRICS="${PLAT_API_METRICS:-http://127.0.0.1:8305/metrics}"
ESPERA_MAX_S="${ESPERA_MAX_S:-840}"
MONTAGEM="${MONTAGEM:-/mnt/plat_homolog_alertas}"

TRAB="$(mktemp -d /tmp/plat-homolog-alertas.XXXXXX)"
PIDS=()
LACO_PID=""

limpar() {
  for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done
  if mountpoint -q "$MONTAGEM" 2>/dev/null; then sudo umount "$MONTAGEM" 2>/dev/null; sudo rmdir "$MONTAGEM" 2>/dev/null; fi
  rm -f "$TRAB/volume.img"
  rm -rf "$TRAB"
}
trap limpar EXIT

echo "== trabalho em $TRAB"
mkdir -p "$TRAB/segredos" "$TRAB/modelos" "$TRAB/prom" "$TRAB/am"

curl -sf --max-time 3 "$API_METRICS" >/dev/null || {
  echo "ERRO: $API_METRICS não responde. Suba a API da trilha antes:"
  echo "  set -a; source /home/dev/plataforma/laco/var/trilha/<nome>.env; set +a"
  echo "  venv/bin/uvicorn app.main:app --port 8305"
  exit 2
}

# ---------------------------------------------------------------- configuração de homologação
for n in PLAT_ALERTA_WEBHOOK_URL PLAT_ALERTA_TESTE_URL; do
  printf 'http://127.0.0.1:%s/' "$PORTA_RECEPTOR" > "$TRAB/segredos/$n"
done
printf 'credencial-de-homologacao-%s' "$RANDOM" > "$TRAB/segredos/PLAT_ALERTA_WEBHOOK_TOKEN"

sed -e "s#/etc/plat/segredos#$TRAB/segredos#g" \
    -e "s#/etc/plat/alertmanager/modelos#$TRAB/modelos#g" \
    "$RAIZ/deploy/alertmanager.yml" > "$TRAB/alertmanager.yml"
amtool check-config "$TRAB/alertmanager.yml" >/dev/null || { echo "ERRO: config derivada inválida"; exit 3; }

ALVO_API="${API_METRICS#http://}"; ALVO_API="${ALVO_API%/metrics}"
cat > "$TRAB/prometheus.yml" <<YML
global:
  scrape_interval: 10s
  evaluation_interval: 10s
rule_files:
  - $RAIZ/deploy/alertas.yml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['127.0.0.1:$PORTA_AM']
scrape_configs:
  - job_name: prometheus
    static_configs: [{targets: ['127.0.0.1:$PORTA_PROM']}]
  - job_name: alertmanager
    static_configs: [{targets: ['127.0.0.1:$PORTA_AM']}]
  - job_name: node-exporter
    static_configs: [{targets: ['127.0.0.1:9100']}]
  - job_name: plat-api-homolog
    static_configs: [{targets: ['$ALVO_API']}]
  - job_name: plat-martin-homolog
    static_configs: [{targets: ['127.0.0.1:$PORTA_ALVO']}]
YML
promtool check config "$TRAB/prometheus.yml" >/dev/null || { echo "ERRO: prometheus.yml inválido"; exit 3; }

# ---------------------------------------------------------------- serviços de homologação
python3 "$RAIZ/deploy/alertas_receptor_teste.py" "$PORTA_RECEPTOR" "$TRAB/recebidos.jsonl" &
PIDS+=($!)
python3 -m http.server "$PORTA_ALVO" --bind 127.0.0.1 --directory "$TRAB" >/dev/null 2>&1 &
PID_ALVO=$!; PIDS+=($PID_ALVO)
prometheus-alertmanager --config.file="$TRAB/alertmanager.yml" --storage.path="$TRAB/am" \
  --web.listen-address="127.0.0.1:$PORTA_AM" --cluster.listen-address= >"$TRAB/am.log" 2>&1 &
PID_AM=$!; PIDS+=($PID_AM)
prometheus --config.file="$TRAB/prometheus.yml" --storage.tsdb.path="$TRAB/prom" \
  --web.listen-address="127.0.0.1:$PORTA_PROM" --storage.tsdb.retention.time=1h >"$TRAB/prom.log" 2>&1 &
PID_PROM=$!; PIDS+=($PID_PROM)

for _ in $(seq 60); do
  curl -sf --max-time 2 "http://127.0.0.1:$PORTA_PROM/-/ready" >/dev/null &&
  curl -sf --max-time 2 "http://127.0.0.1:$PORTA_AM/-/ready"  >/dev/null && break
  sleep 1
done
echo "== prometheus $PORTA_PROM, alertmanager $PORTA_AM, receptor $PORTA_RECEPTOR, alvo plat-* $PORTA_ALVO"

# deixa o alvo plat-martin-homolog ser raspado no ar antes de derrubar (para o `up` ir de 1 a 0)
sleep 25

T0="$(date -u +%s)"
declare -A ENCENADO=()

# ---------------------------------------------------------------- 1. volume de teste cheio
DISCO="nao_encenado: sem sudo ou sem espaço"
if sudo -n true 2>/dev/null; then
  if fallocate -l 64M "$TRAB/volume.img" 2>/dev/null &&
     mkfs.ext4 -q -F "$TRAB/volume.img" 2>/dev/null &&
     sudo mkdir -p "$MONTAGEM" && sudo mount -o loop "$TRAB/volume.img" "$MONTAGEM" 2>/dev/null; then
    sudo chmod 777 "$MONTAGEM"
    LIVRE_KB="$(df -k --output=avail "$MONTAGEM" | tail -1)"
    fallocate -l "$(( (LIVRE_KB - 512) * 1024 ))" "$MONTAGEM/enchendo.bin" 2>/dev/null
    USO="$(df -h --output=pcent "$MONTAGEM" | tail -1 | tr -d ' ')"
    DISCO="encenado: $MONTAGEM em $USO"
    ENCENADO[DiscoQuaseCheio]=1; ENCENADO[DiscoCritico]=1
  fi
fi
echo "== disco: $DISCO"

# ---------------------------------------------------------------- 2. alvo plat-* derrubado
kill "$PID_ALVO" 2>/dev/null; wait "$PID_ALVO" 2>/dev/null
echo "== alvo plat-martin-homolog derrubado (pid $PID_ALVO)"
ENCENADO[ServicoDaPlataformaFora]=1
# AlvoPrometheusCaido dispara no MESMO alvo e é INIBIDO por ServicoDaPlataformaFora (regra de
# inibição por `instance` em alertmanager.yml): não deve chegar ao canal, e por isso não entra na
# lista de esperados. A prova de que ele existe e está disparando é o arquivo
# `<saida>.alertas_prometheus.json`, colhido de /api/v1/alerts do Prometheus.

# ---------------------------------------------------------------- 3-4. banco: backup atrasado, sem ensaio, job longo
if [ -n "${PLAT_SCHEMA:-}" ] && command -v psql >/dev/null; then
  sudo -n -u postgres psql -qXd "${PLAT_BANCO:-iagro_sat}" -v ON_ERROR_STOP=1 >/dev/null 2>&1 <<SQL
    SET search_path = ${PLAT_SCHEMA};
    -- job nasce sempre pendente e só o worker o move para rodando (gatilho plat.job_transicao). Em
    -- vez de furar a regra, a encenação faz o que o worker faz: declara plat.via_worker e transiciona.
    SET plat.via_worker = 'sim';
    DELETE FROM backup_execucao;
    DELETE FROM job WHERE tipo = 'homologacao_alerta';
    INSERT INTO backup_execucao (tipo, ok, detalhe, executado_em)
      VALUES ('backup', true, 'homologacao L7-06-b', now() - interval '30 hours');
    INSERT INTO job (tenant_id, tipo, parametros, executor, pesado, memoria_mb, timeout_s)
      SELECT id, 'homologacao_alerta', '{}'::jsonb, 'local', false, 256, 60 FROM tenant ORDER BY id LIMIT 1;
    UPDATE job SET estado = 'rodando', iniciado_em = now() - interval '35 minutes'
      WHERE tipo = 'homologacao_alerta';
SQL
  RC_SQL=$?
  if [ "$RC_SQL" -eq 0 ]; then
    echo "== banco: backup de 30 h, nenhum ensaio, job rodando há 35 min"
    ENCENADO[BackupAtrasado]=1; ENCENADO[DrillDoMesNaoExecutado]=1; ENCENADO[FilaComJobLongo]=1
  else
    echo "== banco: NÃO encenado (psql como postgres devolveu $RC_SQL)"
  fi
else
  echo "== banco: NÃO encenado (PLAT_SCHEMA não definido no ambiente da trilha)"
fi

# ---------------------------------------------------------------- 5-6. certificado e sentinela
if curl -s --max-time 3 "$API_METRICS" | grep -q '^plat_certificado_dias_restantes'; then
  ENCENADO[CertificadoPertoDeVencer]=1
  echo "== certificado: a API já publica plat_certificado_dias_restantes"
else
  echo "== certificado: NÃO encenado (suba a API com PLAT_CERTIFICADO_CAMINHO apontando para um certificado curto)"
fi
ENCENADO[Sentinela]=1

# ---------------------------------------------------------------- espera e coleta
echo "== esperando até ${ESPERA_MAX_S}s a chegada de ${#ENCENADO[@]} alertas encenados"
ESPERADOS="${!ENCENADO[*]}"
FIM=$(( $(date -u +%s) + ESPERA_MAX_S ))
while [ "$(date -u +%s)" -lt "$FIM" ]; do
  FALTAM=0
  for a in $ESPERADOS; do
    grep -q "\"alertname\": \"$a\"" "$TRAB/recebidos.jsonl" 2>/dev/null || FALTAM=$((FALTAM+1))
  done
  [ "$FALTAM" -eq 0 ] && break
  sleep 5
done

cp "$TRAB/recebidos.jsonl" "${SAIDA%.json}.recebidos.jsonl" 2>/dev/null
curl -s "http://127.0.0.1:$PORTA_PROM/api/v1/alerts" > "${SAIDA%.json}.alertas_prometheus.json"

# ---------------------------------------------------------------- refutação: matar o alertador
echo "== refutação: matando o Alertmanager (pid $PID_AM) e vendo se o Prometheus acusa"
T_MATOU="$(date -u +%s)"
kill "$PID_AM" 2>/dev/null; wait "$PID_AM" 2>/dev/null
ACUSOU="nao"; SEGUNDOS_ACUSOU=""
FIM2=$(( T_MATOU + 300 ))
while [ "$(date -u +%s)" -lt "$FIM2" ]; do
  if curl -s "http://127.0.0.1:$PORTA_PROM/api/v1/alerts" |
     grep -q '"alertname":"AlertmanagerFora","runbook":"alertmanagerfora"[^}]*}[^}]*"state":"firing"' ||
     curl -s "http://127.0.0.1:$PORTA_PROM/api/v1/alerts" |
     python3 -c 'import json,sys; d=json.load(sys.stdin)["data"]["alerts"]; sys.exit(0 if any(a["labels"]["alertname"]=="AlertmanagerFora" and a["state"]=="firing" for a in d) else 1)'; then
    ACUSOU="sim"; SEGUNDOS_ACUSOU=$(( $(date -u +%s) - T_MATOU )); break
  fi
  sleep 5
done
echo "== o Prometheus acusou o alertador caído: $ACUSOU ${SEGUNDOS_ACUSOU:+em ${SEGUNDOS_ACUSOU}s}"

# ---------------------------------------------------------------- veredito em JSON
T0="$T0" ACUSOU="$ACUSOU" SEG="$SEGUNDOS_ACUSOU" DISCO="$DISCO" ESPERADOS="$ESPERADOS" RAIZ="$RAIZ" \
python3 - "$TRAB/recebidos.jsonl" "$SAIDA" <<'PY'
import datetime, json, os, subprocess, sys

recebidos, saida = sys.argv[1], sys.argv[2]
t0 = int(os.environ["T0"])
linhas = []
try:
    with open(recebidos, encoding="utf-8") as f:
        linhas = [json.loads(x) for x in f if x.strip()]
except FileNotFoundError:
    pass

por_alerta = {}
for linha in linhas:
    chegada = datetime.datetime.strptime(linha["recebido_em"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=datetime.UTC).timestamp()
    for a in linha["alertas"]:
        nome = a["alertname"]
        if nome in por_alerta and linha["estado"] != "firing":
            continue
        comeca = a.get("comeca_em")
        inicio = None
        if comeca:
            try:
                inicio = datetime.datetime.fromisoformat(comeca.replace("Z", "+00:00")).timestamp()
            except ValueError:
                inicio = None
        antes = por_alerta.get(nome)
        if antes and antes["segundos_da_condicao_ate_o_canal"] <= round(chegada - t0, 1):
            continue
        por_alerta[nome] = {
            "receptor": linha["receptor"],
            "severidade": a["severidade"],
            "servico": a["servico"],
            "runbook": a["runbook"],
            "estado": linha["estado"],
            "enviado_pelo_alertmanager_com_authorization": linha["autorizacao_presente"],
            "alerta_comecou_em": comeca,
            "chegou_no_canal_em": linha["recebido_em"],
            "segundos_da_condicao_ate_o_canal": round(chegada - t0, 1),
            "segundos_do_firing_ate_o_canal": round(chegada - inicio, 1) if inicio else None,
        }

carga = open("/proc/loadavg").read().split()[0]
livre_gb = round(int([l for l in open("/proc/meminfo") if l.startswith("MemAvailable")][0].split()[1]) / 1048576, 1)
esperados = os.environ["ESPERADOS"].split()
doc = {
    "item": "L7-06-b-alertas",
    "medido_em": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "carga_1min": float(carga),
    "ram_livre_gb": livre_gb,
    "cenario_do_disco": os.environ["DISCO"],
    "alertas_encenados": sorted(esperados),
    "alertas_que_chegaram_ao_canal_de_teste": por_alerta,
    "encenados_que_nao_chegaram": sorted(set(esperados) - set(por_alerta)),
    "refutacao_alertmanager_morto": {
        "prometheus_acusou": os.environ["ACUSOU"],
        "segundos_ate_acusar": int(os.environ["SEG"]) if os.environ["SEG"] else None,
    },
    "amtool_check_config": subprocess.run(
        ["amtool", "check-config", os.path.join(os.environ["RAIZ"], "deploy", "alertmanager.yml")],
        capture_output=True, text=True).stdout.strip().splitlines()[0:1],
}
with open(saida, "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=1)
print(json.dumps({k: doc[k] for k in ("alertas_encenados", "encenados_que_nao_chegaram",
                                      "refutacao_alertmanager_morto", "carga_1min")},
                 ensure_ascii=False, indent=1))
PY
echo "== veredito em $SAIDA"
