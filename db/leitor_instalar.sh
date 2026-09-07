#!/bin/bash
# Papel de LEITURA do banco (item L2-04-a): a role que o Martin — e qualquer outro leitor externo de tile —
# usa para conectar. Sem BYPASSRLS, sem ser dona de nada, só com SELECT nas tabelas de camada e EXECUTE nas
# funções de tile (a migração 20260906T1546_leitor_tiles concede). Aqui mora o que NÃO é migração: LOGIN,
# senha, credential fora do repositório e a linha do pg_hba.conf — a armadilha da casa, porque sem ela a
# role existe, o GRANT existe, e a conexão falha só na primeira consulta.
#
# Uso:  sudo bash db/leitor_instalar.sh [<banco>]
# Variáveis: PLAT_SCHEMA (padrão plat; numa base de trilha/homologação vira plat_t<trilha>, e o papel
# acompanha), PG_HBA, CRED_DIR (padrão /etc/plat/segredos), CRED_DONO (padrão root), PG_RELOAD=nao para não
# recarregar a configuração.
#
# Idempotente de verdade: a última linha da saída é `mudancas: N`; a segunda execução seguida tem de dar 0.
set -euo pipefail
DB=${1:-${PLAT_DB:-iagro_sat}}
SCHEMA=${PLAT_SCHEMA:-plat}
PAPEL="${SCHEMA}_leitor"
PG_HBA=${PG_HBA:-/etc/postgresql/16/main/pg_hba.conf}
CRED_DIR=${CRED_DIR:-/etc/plat/segredos}
# 07/09: dois agentes, em duas trilhas, gravaram credencial de TRILHA em /etc/plat/segredos por deixar o
# padrão passar. O diretório de produção só é aceito quando o ambiente É produção; trilha e homologação
# têm de dizer o seu CRED_DIR de propósito.
if [ "$CRED_DIR" = /etc/plat/segredos ] && [ "${PLAT_AMBIENTE:-}" != producao ]; then
  echo "leitor_instalar: CRED_DIR=/etc/plat/segredos é o diretório de PRODUÇÃO e PLAT_AMBIENTE não é 'producao'." >&2
  echo "  numa trilha, passe CRED_DIR=/home/dev/plataforma/laco/var/trilha/<trilha>_segredos" >&2
  exit 3
fi
CRED="$CRED_DIR/PLAT_DSN_LEITOR"
# dono do credential: root em produção (só o systemd entrega uma cópia à unidade, docs/SEGURANCA.md §1).
# A suíte de teste passa CRED_DONO=<usuário> porque precisa LER o DSN para conectar como papel de leitura.
DONO=${CRED_DONO:-root}
PSQL=(psql -d "$DB" -X -q -v ON_ERROR_STOP=1 -Atc)
[ "$(id -u)" = 0 ] || { echo "rode como root (sudo): mexe em $PG_HBA e em $CRED_DIR" >&2; exit 1; }
MUDANCAS=0

# a) a role existe? (a migração já a cria; aqui é o caso da instalação que ainda não migrou)
if [ "$(sudo -u postgres "${PSQL[@]}" "SELECT count(*) FROM pg_roles WHERE rolname = '$PAPEL'")" = 0 ]; then
  sudo -u postgres "${PSQL[@]}" "CREATE ROLE \"$PAPEL\" NOLOGIN" >/dev/null
  echo "role $PAPEL criada"; MUDANCAS=$((MUDANCAS+1))
fi

# b) atributos: LOGIN sim; superusuário, criação e BYPASSRLS jamais
ATRIB=$(sudo -u postgres "${PSQL[@]}" \
  "SELECT rolcanlogin::int::text||rolsuper::int||rolcreatedb::int||rolcreaterole::int||rolbypassrls::int
     FROM pg_roles WHERE rolname = '$PAPEL'")
if [ "$ATRIB" != "10000" ]; then
  sudo -u postgres "${PSQL[@]}" "ALTER ROLE \"$PAPEL\" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS" >/dev/null
  echo "atributos de $PAPEL alinhados (LOGIN, sem BYPASSRLS)"; MUDANCAS=$((MUDANCAS+1))
fi

# c) credential com o DSN; a senha nunca entra no repositório nem no .env
install -d -m 0700 -o "$DONO" -g "$DONO" "$CRED_DIR"
SENHA=""
if [ -s "$CRED" ]; then
  SENHA=$(sed -nE "s#^postgresql://$PAPEL:([^@]+)@.*#\1#p" "$CRED")
  [ -n "$SENHA" ] || { echo "$CRED não tem a forma postgresql://$PAPEL:<senha>@..." >&2; exit 1; }
fi
if [ -z "$SENHA" ]; then
  SENHA=$(openssl rand -hex 24)
  install -m 0600 -o "$DONO" -g "$DONO" /dev/null "$CRED"
  printf 'postgresql://%s:%s@127.0.0.1:5432/%s' "$PAPEL" "$SENHA" "$DB" > "$CRED"
  sudo -u postgres "${PSQL[@]}" "ALTER ROLE \"$PAPEL\" PASSWORD '$SENHA'" >/dev/null
  echo "credential $CRED criado e senha alinhada"; MUDANCAS=$((MUDANCAS+1))
fi

# d) pg_hba.conf: sem esta linha a conexão do Martin morre na autenticação, não no GRANT
if grep -qE "^host\s+$DB\s+$PAPEL\s" "$PG_HBA"; then
  echo "linha de $PAPEL já existe em $PG_HBA"
else
  printf 'host    %-15s %-15s 127.0.0.1/32            scram-sha-256\n' "$DB" "$PAPEL" >> "$PG_HBA"
  echo "linha de $PAPEL acrescentada em $PG_HBA"; MUDANCAS=$((MUDANCAS+1))
  [ "${PG_RELOAD:-sim}" = "nao" ] || sudo -u postgres "${PSQL[@]}" "SELECT pg_reload_conf()" >/dev/null
fi

# e) a senha do credential é MESMO a do banco? (senão a instalação parece pronta e falha na 1ª consulta)
if ! PGPASSWORD="$SENHA" psql -h 127.0.0.1 -U "$PAPEL" -d "$DB" -X -q -Atc 'SELECT 1' >/dev/null 2>&1; then
  sudo -u postgres "${PSQL[@]}" "ALTER ROLE \"$PAPEL\" PASSWORD '$SENHA'" >/dev/null
  echo "senha de $PAPEL realinhada ao credential"; MUDANCAS=$((MUDANCAS+1))
  PGPASSWORD="$SENHA" psql -h 127.0.0.1 -U "$PAPEL" -d "$DB" -X -q -Atc 'SELECT 1' >/dev/null
fi

echo "mudancas: $MUDANCAS"
