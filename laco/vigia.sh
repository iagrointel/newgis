#!/bin/bash
# Vigia da corrida: mede os quatro recursos que decidem se dá para subir mais agente,
# e diz SOBE, SEGURA ou DESCE. Números medidos em 06/09; ver o plano em
# /home/dev/.claude/plans/fuzzy-spinning-quail.md
RAM=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
SWAP=$(awk '/SwapFree/{print int($2/1024)}' /proc/meminfo)
PSI=$(awk -F'[= ]' '/^some/{print $3}' /proc/pressure/memory 2>/dev/null | head -1)
CON=$(timeout 10 sudo -u postgres psql -d iagro_sat -X -Atc "select count(*) from pg_stat_activity" 2>/dev/null)
CONP=$(timeout 10 sudo -u postgres psql -d iagro_sat -X -Atc "select count(*) from pg_stat_activity where usename like 'plat%'" 2>/dev/null)
DISCO=$(df --output=avail -BG / | tail -1 | tr -dc 0-9)
PGD=$(df --output=avail -BG /mnt/pgdata | tail -1 | tr -dc 0-9)
CARGA=$(cut -d' ' -f1 /proc/loadavg)
printf "RAM %5s MB | troca livre %5s MB | pressao %5s | conexoes %3s/100 (plat %s) | disco / %sG pgdata %sG | carga %s\n" \
  "$RAM" "$SWAP" "${PSI:-0}" "$CON" "$CONP" "$DISCO" "$PGD" "$CARGA"
V=SOBE; M=""
[ "${RAM:-0}" -lt 4000 ] && { V=SEGURA; M="$M memoria<4000;"; }
[ "${RAM:-0}" -lt 2500 ] && { V=DESCE;  M="$M memoria<2500 (piso de OOM);"; }
# troca cheia sozinha NAO e perigo: pagina velha fica la sem custo. O sinal que importa e a
# PRESSAO (/proc/pressure/memory), que mede espera real por pagina. So segura quando os dois batem.
[ "${SWAP:-9999}" -lt 1500 ] && [ "$(echo "${PSI:-0} > 5" | bc -l 2>/dev/null || echo 0)" = 1 ] && { V=SEGURA; M="$M troca cheia E pressao>5;"; }
[ "$(echo "${PSI:-0} > 20" | bc -l 2>/dev/null || echo 0)" = 1 ] && { V=DESCE; M="$M pressao de memoria >20 (precursor de OOM);"; }
[ "${CON:-0}" -gt 70 ] && { V=SEGURA; M="$M conexoes>70;"; }
[ "${CON:-0}" -gt 85 ] && { V=DESCE;  M="$M conexoes>85 (teto 100, a casa inteira usa);"; }
[ "${DISCO:-99}" -lt 20 ] && { V=SEGURA; M="$M disco / <20G;"; }
[ "${PGD:-99}" -lt 20 ] && { V=SEGURA; M="$M pgdata <20G;"; }
# porta duplicada entre trilhas: dois agentes na mesma porta fazem um medir a aplicacao do outro
# e o teste passa medindo a coisa errada (achado da sessao plataforma-d7, 06/09). Porta e recurso
# partilhado da maquina, mesma familia da fila, do trinco e do nome de job do cron.
DUP=$(for pid in $(ss -ltnpH 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u); do
        porta=$(ss -ltnpH 2>/dev/null | grep "pid=$pid," | grep -oE ':81[0-9][0-9]' | head -1)
        arv=$(readlink /proc/$pid/cwd 2>/dev/null)
        [ -n "$porta" ] && echo "$porta $arv"
      done | sort | awk '{if ($1==p && $2!=a) print $1; p=$1; a=$2}' | sort -u)
if [ -n "$DUP" ]; then V=DESCE; M="$M PORTA DUPLICADA entre trilhas: $(echo $DUP | tr '\n' ' ');"; fi
echo "VEREDITO: $V${M:+ ->$M}"
