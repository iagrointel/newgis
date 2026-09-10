#!/bin/bash
# Item L7-06-c, cláusula de retenção. Mede, nesta máquina:
#  1. quanto o journal ocupa e QUANTOS DIAS ele guarda hoje (a retenção real, não a desejada);
#  2. quanto as unidades da plataforma escrevem por dia (para dimensionar 90 dias);
#  3. a variação de `journalctl --disk-usage` depois de uma carga sintética.
# Só lê e escreve no próprio journal; não muda configuração de sistema nenhuma.
set -u
MB=${1:-20}
ETIQUETA=plat_medida_l706c
uso() { echo "$(sudo -n journalctl --disk-usage | grep -oE '[0-9.]+[KMG]' | tail -1) / $(sudo -n du -sb /var/log/journal | cut -f1) bytes"; }

echo "antes: $(uso)"
ANTES=$(uso)
LINHA=$(head -c 900 /dev/urandom | base64 | tr -d '\n')
for _ in $(seq 1 $(( MB * 1024 * 1024 / 1200 )) ); do echo "$LINHA"; done | systemd-cat -t "$ETIQUETA" -p info
sleep 3
sudo -n journalctl --sync 2>/dev/null || true
DEPOIS=$(uso)
echo "depois de ~${MB} MB de carga: $DEPOIS"

PRIMEIRA=$(sudo -n journalctl -o short-iso --no-pager 2>/dev/null | head -1 | awk '{print $1}')
ULTIMA=$(sudo -n journalctl -o short-iso --no-pager -n1 2>/dev/null | awk '{print $1}')
echo "horizonte guardado hoje: de $PRIMEIRA a $ULTIMA"
for u in plat-api plat-worker plat-martin nginx postgresql@16-main; do
  n=$(sudo -n journalctl -u "$u" --since=-24h -o cat --no-pager 2>/dev/null | wc -c)
  echo "volume 24 h de $u: $n bytes"
done
echo "linhas da carga ainda legíveis: $(sudo -n journalctl -t "$ETIQUETA" --no-pager -o cat 2>/dev/null | wc -l)"
