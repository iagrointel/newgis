#!/bin/bash
# Vigia do Martin (medido 10/09/2026, martin 1.15.0): o Martin só descobre as funções de tile (d_<slug>.t_<hex>,
# criadas por plat.camada_tile_garantir) ao SUBIR — SIGHUP não redescobre e não há opção de recarga. Sem isto,
# toda camada publicada depois do início respondia "Source ... does not exist" (502 na porta pública) até alguém
# reiniciar o processo. Este laço conta as funções de tile com a MESMA credencial de leitura do Martin e reinicia
# o processo quando a contagem muda (≈1 s sem tiles; o nginx/app repetem). Sem segredo no arquivo: PLAT_DSN_LEITOR
# vem do ambiente, igual ao próprio Martin.
# uso: PLAT_DSN_LEITOR=... martin_vigia.sh <binário do martin> <config.yaml> <arquivo.pid> [intervalo_s=10]
set -u
MARTIN="$1"; CFG="$2"; PIDF="$3"; INTERVALO="${4:-10}"
: "${PLAT_DSN_LEITOR:?PLAT_DSN_LEITOR ausente no ambiente}"
LOG="${MARTIN_VIGIA_LOG:-${PIDF%.pid}.vigia.log}"
contar() { psql "$PLAT_DSN_LEITOR" -Atqc "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname LIKE 'd\_%' AND p.proname LIKE 't\_%'" 2>/dev/null; }
subir() {
  nohup "$MARTIN" --config "$CFG" >> "${PIDF%.pid}.log" 2>&1 &
  echo $! > "$PIDF"
}
ultimo=$(contar)
echo "$(date -u +%FT%TZ) vigia iniciado: $ultimo funções de tile; pid do martin $(cat "$PIDF" 2>/dev/null)" >> "$LOG"
while sleep "$INTERVALO"; do
  atual=$(contar); [ -n "$atual" ] || continue
  vivo=0; pid=$(cat "$PIDF" 2>/dev/null); [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && vivo=1
  if [ "$atual" != "$ultimo" ] || [ "$vivo" = 0 ]; then
    [ "$vivo" = 1 ] && { kill "$pid"; sleep 1; }
    subir
    echo "$(date -u +%FT%TZ) martin religado: funções $ultimo -> $atual, vivo_antes=$vivo, pid $(cat "$PIDF")" >> "$LOG"
    ultimo=$atual
  fi
done
