#!/usr/bin/env bash
# Aplicador de migrações do plat (ADR 0001 seção 5). Roda como postgres (sudo -u postgres), nunca como plat_app.
#  - lista db/migracoes/ em ordem de aplicação: legado NNN_*.sql (001-048, fechado) e depois carimbo
#    YYYYMMDDTHHMM_*.sql, cada família em ordem lexicográfica (ADR 0014);
#  - nome ausente em plat.versao_migracao: aplica arquivo + INSERT na MESMA transação (psql -1 -f - por stdin);
#  - nome presente com o mesmo sha256: pula;
#  - nome presente com sha diferente: para com código 3 (arquivo aplicado é imutável), salvo se a primeira
#    linha do arquivo for `-- reaplicavel` (só CREATE OR REPLACE): reaplica e atualiza o sha.
# Uso: bash db/migrar.sh            (variáveis: PLAT_DB=iagro_sat, PLAT_MIGRACOES=<dir>)
set -euo pipefail

# --- GUARDA (06/09/2026): migração de TRILHA nunca vai para o schema plat de produção.
# Seis migrações de ramos ainda não juntados foram aplicadas em produção hoje, apesar da regra escrita.
# Regra escrita não segura; a ferramenta segura. Se este script roda a partir de um worktree
# (/home/dev/plataforma/wt/...), o alvo tem de ser uma base de trilha (trilha_ambiente.sh), nunca este.
_raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
case "$_raiz" in /home/dev/plataforma/wt/*)
  if [ -z "${PLAT_TRILHA_ALVO:-}" ]; then
    echo "RECUSADO: db/migrar.sh a partir de worktree ($_raiz) escreveria no schema plat de PRODUÇÃO." >&2
    echo "Use a base da sua trilha: bash /home/dev/plataforma/laco/trilha_ambiente.sh <nome>" >&2
    echo "(ela aplica as migrações do SEU worktree reescritas para plat_t<nome>)." >&2
    exit 9
  fi ;;
esac
DB=${PLAT_DB:-iagro_sat}
DIR=${PLAT_MIGRACOES:-"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/migracoes"}
if [ "$(id -un)" = postgres ]; then PSQL=(psql); else PSQL=(sudo -u postgres psql); fi
PSQL+=(-d "$DB" -X -q -v ON_ERROR_STOP=1)

# a primeira migração cria a tabela; o aplicador garante o mesmo DDL antes de ler
"${PSQL[@]}" -f - <<'SQL'
CREATE SCHEMA IF NOT EXISTS plat AUTHORIZATION postgres;
CREATE TABLE IF NOT EXISTS plat.versao_migracao (
  nome         text PRIMARY KEY,
  sha256       text NOT NULL,
  aplicada_em  timestamptz NOT NULL DEFAULT now(),
  duracao_ms   int NOT NULL,
  aplicada_por text NOT NULL DEFAULT current_user
);
SQL

# Lista as migrações na ORDEM DE APLICAÇÃO. Duas famílias de nome (ADR 0014):
#  - legada `NNN_slug.sql` (001 a 048), FECHADA e imutável;
#  - carimbo de tempo `YYYYMMDDTHHMM_slug.sql`, com 3 hex opcionais quando duas nascem no mesmo minuto.
# Chave de ordenação: prefixo "0" para o legado e "1" para o carimbo, depois o nome. Assim todo o
# legado vem antes de qualquer carimbo e a ordem lexicográfica continua válida dentro de cada família.
listar_migracoes() {
  local d=$1 f
  { for f in "$d"/[0-9][0-9][0-9]_*.sql; do [ -e "$f" ] && printf '0\t%s\n' "$f"; done
    for f in "$d"/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9]*_*.sql; do [ -e "$f" ] && printf '1\t%s\n' "$f"; done
  } | LC_ALL=C sort -t "$(printf '\t')" -k1,1 -k2,2 | cut -f2
}

# pgstac (item L1-01-a): instalado por `pypgstac migrate`, não por um .sql desta pasta (o pacote cria o
# próprio schema `pgstac`, nome fixo). Roda ANTES do laço de .sql abaixo porque a migração
# 20260906T1900_pgstac_privilegios.sql concede pgstac_read/pgstac_ingest a plat_app e precisa dos dois papéis
# já existentes. Idempotente (db/pgstac_instalar.sh só reaplica se a versão instalada mudou).
PLAT_DB="$DB" PLAT_SCHEMA=plat bash "$(dirname "${BASH_SOURCE[0]}")/pgstac_instalar.sh"

aplicadas=0; puladas=0; reaplicadas=0
shopt -s nullglob
mapfile -t arquivos < <(listar_migracoes "$DIR")
if [ ${#arquivos[@]} -eq 0 ]; then echo "nenhuma migração em $DIR" >&2; exit 2; fi
for arq in "${arquivos[@]}"; do
  nome=$(basename "$arq" .sql)
  sha=$(sha256sum "$arq" | cut -d' ' -f1)
  atual=$("${PSQL[@]}" -Atc "SELECT sha256 FROM plat.versao_migracao WHERE nome = '$nome'")
  modo=inserir
  if [ -n "$atual" ]; then
    if [ "$atual" = "$sha" ]; then echo "igual      $nome"; puladas=$((puladas+1)); continue; fi
    if [ "$(head -n1 "$arq" | tr -d '[:space:]')" = "--reaplicavel" ]; then modo=atualizar
    else echo "DIVERGENTE $nome: sha aplicado $atual, arquivo $sha (arquivo aplicado é imutável; correção vai em arquivo novo)" >&2; exit 3; fi
  fi
  if [ "$modo" = inserir ]; then
    registro="INSERT INTO plat.versao_migracao(nome, sha256, duracao_ms) VALUES ('$nome', '$sha', (extract(epoch from (clock_timestamp() - now())) * 1000)::int);"
  else
    registro="UPDATE plat.versao_migracao SET sha256 = '$sha', aplicada_em = now(), duracao_ms = (extract(epoch from (clock_timestamp() - now())) * 1000)::int, aplicada_por = current_user WHERE nome = '$nome';"
  fi
  t0=$(date +%s%N)
  { cat "$arq"; printf '\n%s\n' "$registro"; } | "${PSQL[@]}" -1 -f -
  ms=$(( ($(date +%s%N) - t0) / 1000000 ))
  if [ "$modo" = inserir ]; then echo "aplicada   $nome (${ms} ms)"; aplicadas=$((aplicadas+1)); else echo "reaplicada $nome (${ms} ms)"; reaplicadas=$((reaplicadas+1)); fi
done
echo "migracoes: aplicadas $aplicadas · reaplicadas $reaplicadas · iguais $puladas · pendentes 0"
