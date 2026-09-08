#!/usr/bin/env bash
# Instala/atualiza o pgstac (schema `pgstac`, ADR 0001 seção 5; item L1-01-a) e registra a versão aplicada em
# <PLAT_SCHEMA>.versao_migracao — a MESMA tabela e o mesmo formato das migrações SQL comuns — para que
# `pypgstac migrate` apareça no mesmo painel de versão do resto do `plat`, mesmo sendo instalado por uma
# ferramenta Python (pypgstac), não por um arquivo .sql desta pasta.
#
# O pgstac não aceita nome de schema por parâmetro (pypgstac cria sempre `CREATE SCHEMA pgstac`, fixo no
# próprio pacote): é infraestrutura GLOBAL ao banco, como uma extensão. Por isso este script NÃO faz parte
# do laço por-trilha de `laco/trilha_reescrever.py` (que reescreve `plat`->`plat_t<trilha>`) — ele instala o
# pgstac uma vez por banco e registra a aplicação no schema da trilha que o chamou (PLAT_SCHEMA), para que
# cada trilha tenha o próprio registro de "eu já chequei a versão do pgstac aqui", sem duplicar o schema.
#
# Chamado por db/migrar.sh (produção, schema `plat`, banco de produção) e, manualmente, por quem prepara uma
# base de trilha (depois de `laco/trilha_ambiente.sh`, com PLAT_SCHEMA=plat_t<trilha>): as duas chamadas
# apontam pro MESMO schema `pgstac` (é global), mas registram a versão em tabelas de controle diferentes.
#
# Uso: PLAT_DB=iagro_sat PLAT_SCHEMA=plat_tpgstac bash db/pgstac_instalar.sh
set -euo pipefail
DB=${PLAT_DB:-iagro_sat}
SCHEMA=${PLAT_SCHEMA:-plat}
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$RAIZ/venv"
[ -x "$VENV/bin/pypgstac" ] || { echo "pypgstac não está no venv $VENV — instalação é decisão do dono, não deste script" >&2; exit 2; }

if [ "$(id -un)" = postgres ]; then PSQL=(psql -d "$DB" -X -q -v ON_ERROR_STOP=1); SUDOPG=(); else PSQL=(sudo -u postgres psql -d "$DB" -X -q -v ON_ERROR_STOP=1); SUDOPG=(sudo -u postgres); fi

"${PSQL[@]}" -c "CREATE EXTENSION IF NOT EXISTS btree_gist" >/dev/null

VERSAO=$("$VENV/bin/pip" show pypgstac 2>/dev/null | awk -F': ' '/^Version:/{print $2}')
[ -n "$VERSAO" ] || { echo "não consegui ler a versão do pypgstac instalado" >&2; exit 2; }
NOME="pgstac-migrate-$VERSAO"

# tabela de controle da TRILHA/schema que chamou (a mesma DDL da 001_fundacao, para uma base nova sem `plat`
# ainda aplicado — o caso normal é ela já existir, criada por trilha_ambiente.sh ou db/migrar.sh)
"${PSQL[@]}" -f - <<SQL >/dev/null
CREATE SCHEMA IF NOT EXISTS $SCHEMA AUTHORIZATION postgres;
CREATE TABLE IF NOT EXISTS $SCHEMA.versao_migracao (
  nome text PRIMARY KEY, sha256 text NOT NULL, aplicada_em timestamptz NOT NULL DEFAULT now(),
  duracao_ms int NOT NULL, aplicada_por text NOT NULL DEFAULT current_user);
SQL

JA=$("${PSQL[@]}" -Atc "SELECT 1 FROM $SCHEMA.versao_migracao WHERE nome = '$NOME'" || true)
if [ "$JA" = "1" ]; then
  echo "pgstac $VERSAO já registrado em $SCHEMA.versao_migracao (nada a fazer)"
  exit 0
fi

DSN="postgresql:///$DB?host=/var/run/postgresql"
ini=$(date +%s%3N)
"${SUDOPG[@]}" "$VENV/bin/pypgstac" migrate --dsn "$DSN"
dur=$(( $(date +%s%3N) - ini ))
SHA=$(printf '%s' "$VERSAO" | sha256sum | cut -d' ' -f1)
"${PSQL[@]}" -c "INSERT INTO $SCHEMA.versao_migracao(nome, sha256, duracao_ms, aplicada_por) VALUES ('$NOME','$SHA',$dur,'pypgstac') ON CONFLICT (nome) DO NOTHING" >/dev/null
echo "pgstac migrado para $VERSAO em ${dur}ms; registrado como $NOME em $SCHEMA.versao_migracao"
