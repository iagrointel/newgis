#!/bin/bash
# Vigia do Martin para unidade systemd (item "unidades systemd de trilha", 10/09/2026). Mesmo motivo do
# irmão `martin_vigia.sh` (nohup, ainda em uso por trilhas sem unidade systemd — NÃO editar aquele
# arquivo aqui): o Martin só descobre função de tile nova (d_<slug>.t_<hex>) ao SUBIR — SIGHUP não
# recarrega e não há opção de reload (medido 10/09/2026, martin 1.15.0). Sem vigia, uma camada publicada
# depois do boot da unidade responde 502 "Source ... does not exist" até alguém reiniciar à mão.
#
# Diferença para o irmão nohup: em vez de matar/subir o BINÁRIO com PID em arquivo, este pede ao PRÓPRIO
# systemd para reiniciar a UNIDADE (`sudo systemctl restart <unidade>`) — assim o processo do Martin
# nunca fica fora do controle do systemd (o gerador de unidades desta trilha existe exatamente para
# tirar processo de baixo de PID solto em /tmp). `dev` tem sudo NOPASSWD nesta máquina (medido 10/09) —
# sem isso a unidade teria de rodar como root só para religar a irmã, o que não vale a pena.
#
# uso: PLAT_DSN_LEITOR=... martin_vigia_systemd.sh <unidade-systemd-do-martin> [intervalo_s=10]
set -u
UNIDADE="${1:?uso: martin_vigia_systemd.sh <unidade-systemd-do-martin> [intervalo_s=10]}"
INTERVALO="${2:-10}"
: "${PLAT_DSN_LEITOR:?PLAT_DSN_LEITOR ausente no ambiente (EnvironmentFile da unidade)}"

contar() {
  psql "$PLAT_DSN_LEITOR" -Atqc \
    "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname LIKE 'd\_%' AND p.proname LIKE 't\_%'" \
    2>/dev/null
}

ultimo=$(contar)
echo "$(date -u +%FT%TZ) vigia systemd iniciado para $UNIDADE: $ultimo função(ões) de tile"
while sleep "$INTERVALO"; do
  atual=$(contar); [ -n "$atual" ] || continue
  ativo=$(systemctl is-active "$UNIDADE" 2>/dev/null)
  if [ "$atual" != "$ultimo" ] || [ "$ativo" != "active" ]; then
    sudo -n systemctl restart "$UNIDADE"
    echo "$(date -u +%FT%TZ) $UNIDADE religada: funções $ultimo -> $atual, estava '$ativo'"
    ultimo=$atual
  fi
done
