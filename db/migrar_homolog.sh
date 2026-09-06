#!/usr/bin/env bash
# Aplicador de migrações do AMBIENTE DE HOMOLOGAÇÃO (item L7-31; docs/HOMOLOGACAO.md). Mesmo banco
# iagro_sat de sempre (nunca um banco novo — disco a 98%), mesmo conjunto de arquivos db/migracoes/,
# mas cada um passa por db/reescrever_homolog.py antes do psql: schema `plat`/`plat_trabalho` e
# papel/canal `plat_app`/`plat_worker`/`plat_job` viram `_homolog`, sem tocar o schema `plat` de
# produção nem as roles `plat_app`/`plat_worker` de produção (o script cria papéis NOVOS: plat_homolog_app,
# plat_homolog_worker). Controle de versão próprio: plat_homolog.versao_migracao (nunca plat.versao_migracao).
# Uso: bash db/migrar_homolog.sh            (variáveis: PLAT_DB=iagro_sat, PLAT_MIGRACOES=<dir>)
set -euo pipefail
DIR_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB=${PLAT_DB:-iagro_sat}
DIR=${PLAT_MIGRACOES:-"$DIR_REPO/db/migracoes"}
PY="$DIR_REPO/venv/bin/python"
REESCREVER="$DIR_REPO/db/reescrever_homolog.py"
if [ "$(id -un)" = postgres ]; then PSQL=(psql); else PSQL=(sudo -u postgres psql); fi
PSQL+=(-d "$DB" -X -q -v ON_ERROR_STOP=1)

# a primeira migração cria a tabela de controle PRÓPRIA do homolog; nunca a de produção
"${PSQL[@]}" -f - <<'SQL'
CREATE SCHEMA IF NOT EXISTS plat_homolog AUTHORIZATION postgres;
CREATE TABLE IF NOT EXISTS plat_homolog.versao_migracao (
  nome         text PRIMARY KEY,
  sha256       text NOT NULL,
  aplicada_em  timestamptz NOT NULL DEFAULT now(),
  duracao_ms   int NOT NULL,
  aplicada_por text NOT NULL DEFAULT current_user
);
SQL

aplicadas=0; puladas=0; reaplicadas=0
shopt -s nullglob
arquivos=("$DIR"/[0-9][0-9][0-9]_*.sql)
if [ ${#arquivos[@]} -eq 0 ]; then echo "nenhuma migração em $DIR" >&2; exit 2; fi
for arq in "${arquivos[@]}"; do
  nome=$(basename "$arq" .sql)
  transformado_arq=$(mktemp)
  "$PY" "$REESCREVER" "$arq" > "$transformado_arq"
  sha=$(sha256sum "$transformado_arq" | cut -d' ' -f1)
  atual=$("${PSQL[@]}" -Atc "SELECT sha256 FROM plat_homolog.versao_migracao WHERE nome = '$nome'")
  modo=inserir
  if [ -n "$atual" ]; then
    if [ "$atual" = "$sha" ]; then echo "igual      $nome"; puladas=$((puladas+1)); rm -f "$transformado_arq"; continue; fi
    if [ "$(head -n1 "$arq" | tr -d '[:space:]')" = "--reaplicavel" ]; then modo=atualizar
    else
      echo "DIVERGENTE $nome (homolog): sha aplicado $atual, transformado $sha (arquivo aplicado é imutável)" >&2
      rm -f "$transformado_arq"; exit 3
    fi
  fi
  if [ "$modo" = inserir ]; then
    registro="INSERT INTO plat_homolog.versao_migracao(nome, sha256, duracao_ms) VALUES ('$nome', '$sha', (extract(epoch from (clock_timestamp() - now())) * 1000)::int);"
  else
    registro="UPDATE plat_homolog.versao_migracao SET sha256 = '$sha', aplicada_em = now(), duracao_ms = (extract(epoch from (clock_timestamp() - now())) * 1000)::int, aplicada_por = current_user WHERE nome = '$nome';"
  fi
  t0=$(date +%s%N)
  { cat "$transformado_arq"; printf '\n%s\n' "$registro"; } | "${PSQL[@]}" -1 -f -
  ms=$(( ($(date +%s%N) - t0) / 1000000 ))
  rm -f "$transformado_arq"
  if [ "$modo" = inserir ]; then echo "aplicada   $nome (${ms} ms)"; aplicadas=$((aplicadas+1)); else echo "reaplicada $nome (${ms} ms)"; reaplicadas=$((reaplicadas+1)); fi
done
echo "migracoes homolog: aplicadas $aplicadas · reaplicadas $reaplicadas · iguais $puladas · pendentes 0"
