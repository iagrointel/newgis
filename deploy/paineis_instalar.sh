#!/usr/bin/env bash
# Instala os painéis do item L7-06-d no Grafana DA CASA (perfil hospedado, 127.0.0.1:3000).
#
# O Grafana da casa roda em contêiner (`iagro-grafana`) com dois bind mounts fixos:
# /opt/monitoring/grafana/provisioning e /opt/monitoring/grafana/dashboards. Este script escreve
# dentro deles; NÃO recria o contêiner e NÃO mexe no provedor `iagrointel` que já existia.
#
# ⚠ Limite conhecido e deliberado: o provedor `iagrointel` da casa já varre
# /var/lib/grafana/dashboards inteiro, recursivamente. Se acrescentássemos AQUI o nosso provedor
# `plat` apontando para a subpasta, os dois disputariam os mesmos arquivos e o Grafana recusaria o
# segundo ("dashboard already provisioned by another provider"). Então no hospedado os painéis entram
# pelo provedor da casa, na subpasta `plat/`; o provedor próprio de deploy/grafana/provisioning é o
# que vale no appliance (perfil `observabilidade`), onde o Grafana é nosso e o mount é nosso. Trocar
# isso no hospedado exige recriar o contêiner da casa — decisão do dono, não deste script.
#
# Idempotente: rodar 2× deixa o mesmo estado e o mesmo uid em cada painel (o uid está no arquivo).
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINO="${DESTINO:-/opt/monitoring/grafana/dashboards/plat}"
FONTES="${FONTES:-/opt/monitoring/grafana/provisioning/datasources}"
GRAFANA="${GRAFANA:-http://127.0.0.1:3000}"

sudo mkdir -p "$DESTINO"
sudo cp "$RAIZ"/deploy/grafana/paineis/*.json "$DESTINO/"
sudo cp "$RAIZ/deploy/grafana/provisioning/datasources/plat-prometheus.yml" "$FONTES/"
sudo chmod 644 "$DESTINO"/*.json "$FONTES/plat-prometheus.yml"

# a fonte de dado só é lida na subida; os painéis, a cada updateIntervalSeconds do provedor da casa
docker restart iagro-grafana >/dev/null
for _ in $(seq 90); do
  curl -sf --max-time 2 "$GRAFANA/api/health" >/dev/null && break
  sleep 1
done
echo "instalado em $DESTINO; confira com:"
echo "  curl -s -u admin:<senha> $GRAFANA/api/dashboards/uid/plat-visao-geral | head -c 200"
