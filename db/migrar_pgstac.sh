#!/usr/bin/env bash
# Passo pgstac do aplicador (item L1-01-a; ADR 0011). Chamado por db/migrar.sh DEPOIS das migrações SQL (a 046 cria
# plat.versao_pgstac). Faz, como postgres: `pypgstac migrate` (schema pgstac, roles pgstac_admin/read/ingest, versão
# lida em pgstac.get_version()); GRANT pgstac_read + pgstac_ingest a plat_app e plat_worker (NUNCA pgstac_admin —
# essa role fica só com o migrate); registro em plat.versao_pgstac. Idempotente: com o pgstac já na versão do pypgstac
# da venv, o migrate só confere e nada muda. Nunca imprime a palavra "igual " (o teste de db/migrar.sh conta essa
# palavra por migração SQL).
# Uso: bash db/migrar_pgstac.sh   (variáveis: PLAT_DB=iagro_sat, PLAT_PYPGSTAC=<caminho do binário>)
set -euo pipefail
DB=${PLAT_DB:-iagro_sat}
RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYPGSTAC=${PLAT_PYPGSTAC:-"$RAIZ/venv/bin/pypgstac"}
if [ ! -x "$PYPGSTAC" ]; then
  echo "pgstac: $PYPGSTAC ausente (PYTHONNOUSERSITE=1 venv/bin/pip install -r requirements.txt)" >&2; exit 4
fi
if [ "$(id -un)" = postgres ]; then COMO=(env); PSQL=(psql); else COMO=(sudo -u postgres env); PSQL=(sudo -u postgres psql); fi
PSQL+=(-d "$DB" -X -q -v ON_ERROR_STOP=1)
DSN="postgresql:///$DB"   # socket local, peer como postgres; nunca senha em linha de comando
pacote=$("$(dirname "$PYPGSTAC")/python" -c 'import pypgstac; print(pypgstac.__version__)')

# o nome qualificado não pode aparecer na consulta antes de o schema existir (erro de análise, não de execução)
if [ "$("${PSQL[@]}" -Atc "SELECT count(*) FROM pg_namespace WHERE nspname = 'pgstac'")" = 1 ]; then
  antes=$("${PSQL[@]}" -Atc "SELECT pgstac.get_version()")
else antes=""; fi
t0=$(date +%s%N)
# HOME de postgres: o psycopg lê ~/.pgpass e ~/.pg_service.conf; PYTHONNOUSERSITE evita ~/.local de quem chama
"${COMO[@]}" HOME=/var/lib/postgresql PYTHONNOUSERSITE=1 "$PYPGSTAC" migrate --dsn "$DSN" >/dev/null
ms=$(( ($(date +%s%N) - t0) / 1000000 ))
depois=$("${PSQL[@]}" -Atc "SELECT pgstac.get_version()")

"${PSQL[@]}" -f - <<SQL
SET client_min_messages = warning;
GRANT pgstac_read, pgstac_ingest TO plat_app;
GRANT pgstac_read, pgstac_ingest TO plat_worker;
-- pgstac_admin nunca: só o migrate a usa (portão do item; ADR 0011 D2)
DO \$\$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_auth_members am JOIN pg_roles r ON r.oid = am.roleid JOIN pg_roles m ON m.oid = am.member
             WHERE r.rolname = 'pgstac_admin' AND m.rolname IN ('plat_app', 'plat_worker')) THEN
    REVOKE pgstac_admin FROM plat_app, plat_worker;
  END IF;
END \$\$;
INSERT INTO plat.versao_pgstac (versao, pypgstac) VALUES ('$depois', '$pacote') ON CONFLICT (versao) DO NOTHING;
SQL
if [ "$antes" = "$depois" ]; then echo "pgstac     $depois conferido (${ms} ms)"
else echo "pgstac     ${antes:-ausente} -> $depois aplicado (${ms} ms)"; fi
