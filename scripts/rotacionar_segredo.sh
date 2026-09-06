#!/usr/bin/env bash
# Rotaciona um segredo do plat sem reinstalar e sem editar unidade systemd (item L7-19-segredos-e-
# certificados; docs/SEGURANCA.md secao "segredos e certificados"). Gera valor novo, atualiza a role no
# banco quando o segredo e uma senha de banco, grava o credential (/etc/plat/segredos/<NOME>, 0600, dono
# root) e reinicia so a unidade que le aquele segredo — uma reinicializacao por vez, o tempo de baixa e o
# tempo do "systemctl restart" (poucos segundos), nunca mais.
#
# Uso: sudo bash scripts/rotacionar_segredo.sh <PLAT_SECRET|PLAT_DSN_WORKER|PLAT_DSN|PLAT_GARAGE_ADMIN_TOKEN>
#      sudo bash scripts/rotacionar_segredo.sh PLAT_GARAGE_S3 <slug-do-inquilino>
#
# PLAT_SECRET (le plat-api): HMAC de URL assinada de objeto (app/objetos.py) e cifra do segredo TOTP em
#   repouso (app/auth/totp.py). Trocar invalida NA HORA qualquer URL assinada emitida antes (o cliente
#   pede outra) e torna o totp_secret ja cifrado ILEGIVEL para todo usuario com 2FA ligado — o proprio
#   codigo ja trata isso (app/auth/rotas_login.py: "segredo ilegivel (PLAT_SECRET trocado): so recuperacao
#   vale"), a pessoa entra com codigo de recuperacao e recadastra o 2FA. Avisar antes de rotacionar em
#   producao com usuarios 2FA ativos.
# PLAT_DSN_WORKER (le plat-worker): senha da role `plat_worker`, a unica com EXECUTE nas funcoes que
#   mudam estado de job de qualquer inquilino (achado do adversario no T2, L0-05). Rotacionar troca a
#   senha no Postgres ANTES de trocar o credential e reiniciar, para nunca existir um instante em que o
#   worker novo suba com senha que o banco ainda nao aceita.
# PLAT_DSN (le plat-api E plat-worker): senha da role `plat_app`, a role de toda consulta da aplicacao.
#   Mesma ordem do PLAT_DSN_WORKER (banco primeiro, credential depois), com uma diferenca: DUAS unidades
#   leem esse segredo, entao ha duas reinicializacoes, uma de cada vez, api antes do worker.
# PLAT_GARAGE_ADMIN_TOKEN (le plat-api e plat-worker): token de administracao do armazenamento de objetos.
#   Rotacionar aqui cria um token NOVO e gerenciado pelo proprio Garage (`garage admin-token create`, v2) e
#   passa a app a usa-lo. O token estatico do `garage.toml` continua valendo ate o dono tira-lo do arquivo e
#   reiniciar o daemon `plataforma-garage` (passo do dono, docs/AMBIENTES.md secao 5) — enquanto ele existir,
#   esta rotacao troca a credencial da APP, nao mata a credencial antiga.
# PLAT_GARAGE_S3 <slug> (nenhuma unidade le do disco): par de chaves S3 (RW e RO) do bucket de UM inquilino.
#   Vive em `plat.arquivo_bucket`, nao em arquivo, e a app le do banco a cada chamada — por isso esta e a
#   unica rotacao com ZERO reinicializacao e zero janela de indisponibilidade.
set -euo pipefail
NOME=${1:?uso: sudo bash scripts/rotacionar_segredo.sh <PLAT_SECRET|PLAT_DSN_WORKER|PLAT_DSN|PLAT_GARAGE_ADMIN_TOKEN|PLAT_GARAGE_S3 <slug>>}
ALVO=${2:-}
DB=${PLAT_DB:-iagro_sat}
CRED_DIR=/etc/plat/segredos
ARQUIVO="$CRED_DIR/$NOME"
INICIO=$SECONDS
APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
GARAGE_BIN=${GARAGE_BIN:-/home/dev/plataforma/pipeline/bin/garage}
GARAGE_CONFIG=${GARAGE_CONFIG:-/home/dev/plataforma/pipeline/garage/garage.toml}

[ "$(id -u)" -eq 0 ] || { echo "rode como root: sudo bash scripts/rotacionar_segredo.sh $NOME" >&2; exit 1; }
if [ "$NOME" != "PLAT_GARAGE_S3" ] && [ ! -f "$ARQUIVO" ]; then
  echo "$ARQUIVO não existe (rode install.sh primeiro para criar o credential)" >&2; exit 1
fi
PSQL=(sudo -u postgres psql -d "$DB" -X -q -v ON_ERROR_STOP=1)

PORTA_API=$(grep -oP -- '--port \K[0-9]+' /etc/systemd/system/plat-api.service 2>/dev/null || echo 8150)
# "unidade:porta do /saude" — a rotacao reinicia UMA de cada vez, na ordem em que aparecem aqui
UNIDADES=()

case "$NOME" in
  PLAT_SECRET)
    UNIDADES=("plat-api:$PORTA_API")
    NOVO=$(openssl rand -hex 32)
    printf '%s' "$NOVO" > "$ARQUIVO"
    echo "PLAT_SECRET novo gerado e gravado em $ARQUIVO"
    echo "aviso: URL de objeto assinada antes desta troca para de validar; totp_secret já cifrado fica"
    echo "ilegível (usuário com 2FA entra com código de recuperação e recadastra — comportamento já"
    echo "tratado em app/auth/rotas_login.py, não é uma falha nova)"
    ;;
  PLAT_DSN_WORKER)
    UNIDADES=("plat-worker:8153")
    ANTIGO_DSN=$(cat "$ARQUIVO")
    ANTIGA_SENHA=$(sed -nE 's#^postgresql://plat_worker:([^@]+)@.*#\1#p' <<<"$ANTIGO_DSN")
    HOST_DB=$(sed -nE 's#^postgresql://plat_worker:[^@]+@([^/]+)/.*#\1#p' <<<"$ANTIGO_DSN")
    [ -n "$ANTIGA_SENHA" ] && [ -n "$HOST_DB" ] || { echo "$ARQUIVO não tem a forma postgresql://plat_worker:<senha>@<host>/<db>" >&2; exit 1; }
    NOVA_SENHA=$(openssl rand -hex 16)
    NOVO_DSN="postgresql://plat_worker:${NOVA_SENHA}@${HOST_DB}/${DB}"
    # 1. banco primeiro: a senha nova já autentica antes de qualquer processo tentar usá-la
    printf "ALTER ROLE plat_worker PASSWORD '%s';\n" "$NOVA_SENHA" | "${PSQL[@]}" -f -
    echo "senha de plat_worker trocada no banco"
    # 2. credential depois
    printf '%s' "$NOVO_DSN" > "$ARQUIVO"
    echo "PLAT_DSN_WORKER novo gravado em $ARQUIVO"
    # 3. prova de que o valor antigo morreu (portão: "adversário... qualquer um em claro... = refutado";
    #    aqui é o inverso — provar que o antigo NÃO funciona mais)
    if PGPASSWORD="$ANTIGA_SENHA" psql -X -q -h "${HOST_DB%%:*}" -p "${HOST_DB#*:}" -U plat_worker -d "$DB" -Atc "SELECT 1" >/dev/null 2>&1; then
      echo "ATENÇÃO: a senha anterior de plat_worker ainda autentica no banco (esperado: falhar)" >&2
      exit 2
    fi
    echo "confirmado: a senha anterior de plat_worker não autentica mais"
    ;;
  PLAT_DSN)
    # senha da role plat_app; lida por plat-api E por plat-worker (o worker abre conexao de aplicacao alem
    # da de estado de job). Banco primeiro, credential depois, reinicio por ultimo — igual ao worker.
    UNIDADES=("plat-api:$PORTA_API" "plat-worker:8153")
    ANTIGO_DSN=$(cat "$ARQUIVO")
    ANTIGA_SENHA=$(sed -nE 's#^postgresql://plat_app:([^@]+)@.*#\1#p' <<<"$ANTIGO_DSN")
    HOST_DB=$(sed -nE 's#^postgresql://plat_app:[^@]+@([^/]+)/.*#\1#p' <<<"$ANTIGO_DSN")
    [ -n "$ANTIGA_SENHA" ] && [ -n "$HOST_DB" ] || { echo "$ARQUIVO não tem a forma postgresql://plat_app:<senha>@<host>/<db>" >&2; exit 1; }
    NOVA_SENHA=$(openssl rand -hex 16)
    printf "ALTER ROLE plat_app PASSWORD '%s';\n" "$NOVA_SENHA" | "${PSQL[@]}" -f -
    echo "senha de plat_app trocada no banco"
    printf '%s' "postgresql://plat_app:${NOVA_SENHA}@${HOST_DB}/${DB}" > "$ARQUIVO"
    echo "PLAT_DSN novo gravado em $ARQUIVO"
    if PGPASSWORD="$ANTIGA_SENHA" psql -X -q -h "${HOST_DB%%:*}" -p "${HOST_DB#*:}" -U plat_app -d "$DB" -Atc "SELECT 1" >/dev/null 2>&1; then
      echo "ATENÇÃO: a senha anterior de plat_app ainda autentica no banco (esperado: falhar)" >&2
      exit 2
    fi
    echo "confirmado: a senha anterior de plat_app não autentica mais"
    ;;
  PLAT_GARAGE_ADMIN_TOKEN)
    # Garage v2 tem token de administracao gerenciado pelo proprio servidor (`garage admin-token`), com
    # escopo e validade — diferente do `admin_token` estatico do garage.toml, que so sai de la com edicao do
    # arquivo e reinicio do daemon (passo do dono). Aqui criamos um token gerenciado novo e apontamos a app
    # para ele; o token gerenciado ANTERIOR (se houver) e apagado ao fim, o estatico nunca.
    UNIDADES=("plat-api:$PORTA_API" "plat-worker:8153")
    [ -x "$GARAGE_BIN" ] || { echo "binário do garage não encontrado: $GARAGE_BIN (defina GARAGE_BIN)" >&2; exit 1; }
    [ -r "$GARAGE_CONFIG" ] || { echo "configuração do garage ilegível: $GARAGE_CONFIG (defina GARAGE_CONFIG)" >&2; exit 1; }
    GARAGE=("$GARAGE_BIN" -c "$GARAGE_CONFIG")
    NOME_NOVO="plat-app-$(date +%Y%m%d%H%M%S)"
    ANTERIORES=$("${GARAGE[@]}" admin-token list | awk 'NR>1 && $3 ~ /^plat-app-/ {print $3}' || true)
    NOVO=$("${GARAGE[@]}" admin-token create --quiet "$NOME_NOVO")
    [ -n "$NOVO" ] || { echo "garage admin-token create não devolveu token" >&2; exit 1; }
    printf '%s' "$NOVO" > "$ARQUIVO"
    echo "token de administração gerenciado $NOME_NOVO criado e gravado em $ARQUIVO"
    ADMIN_URL=${PLAT_GARAGE_ADMIN_URL:-http://127.0.0.1:3903}
    curl -fsS -m 5 -H "Authorization: Bearer $NOVO" "$ADMIN_URL/v2/ListBuckets" >/dev/null \
      || { echo "o token novo não foi aceito por $ADMIN_URL/v2/ListBuckets" >&2; exit 2; }
    echo "confirmado: o token novo é aceito pela API de administração"
    ;;
  PLAT_GARAGE_S3)
    # par RW/RO do bucket de UM inquilino, guardado em plat.arquivo_bucket. Nenhuma unidade le do disco:
    # a app resolve o bucket e as chaves no banco a cada chamada, entao a troca vale na consulta seguinte,
    # sem reinicio e sem janela. Exige token de administracao (criar chave e dar permissao no bucket).
    SLUG=${ALVO:?uso: sudo bash scripts/rotacionar_segredo.sh PLAT_GARAGE_S3 <slug-do-inquilino>}
    ADMIN_URL=${PLAT_GARAGE_ADMIN_URL:-http://127.0.0.1:3903}
    TOKEN=$(cat "$CRED_DIR/PLAT_GARAGE_ADMIN_TOKEN" 2>/dev/null || sed -nE 's/^PLAT_GARAGE_ADMIN_TOKEN=//p' "$APP_DIR/.env" | head -n1)
    [ -n "$TOKEN" ] || { echo "sem PLAT_GARAGE_ADMIN_TOKEN (nem em $CRED_DIR nem no .env)" >&2; exit 1; }
    LINHA=$("${PSQL[@]}" -Atc "SELECT b.bucket_id||'|'||b.bucket_alias||'|'||b.chave_rw_id||'|'||b.chave_ro_id FROM plat.arquivo_bucket b JOIN plat.tenant t ON t.id=b.tenant_id WHERE t.slug='$SLUG'")
    [ -n "$LINHA" ] || { echo "inquilino '$SLUG' não tem bucket registrado em plat.arquivo_bucket" >&2; exit 1; }
    IFS='|' read -r BUCKET_ID ALIAS RW_ANTIGA RO_ANTIGA <<<"$LINHA"
    CARIMBO=$(date +%Y%m%d%H%M%S)
    criar_chave() {  # $1 = nome; ecoa "<id> <segredo>"
      curl -fsS -m 10 -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
        -d "{\"name\": \"$1\"}" "$ADMIN_URL/v2/CreateKey" \
        | "$APP_DIR/venv/bin/python" -c 'import json,sys; k=json.load(sys.stdin); print(k["accessKeyId"], k["secretAccessKey"])'
    }
    permitir() {  # $1 = accessKeyId, $2/$3/$4 = read/write/owner
      curl -fsS -m 10 -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
        -d "{\"bucketId\": \"$BUCKET_ID\", \"accessKeyId\": \"$1\", \"permissions\": {\"read\": $2, \"write\": $3, \"owner\": $4}}" \
        "$ADMIN_URL/v2/AllowBucketKey" >/dev/null
    }
    read -r RW_ID RW_SEG < <(criar_chave "$ALIAS-rw-$CARIMBO")
    read -r RO_ID RO_SEG < <(criar_chave "$ALIAS-ro-$CARIMBO")
    permitir "$RW_ID" true true true
    permitir "$RO_ID" true false false
    "${PSQL[@]}" -c "UPDATE plat.arquivo_bucket SET chave_rw_id='$RW_ID', chave_rw_segredo='$RW_SEG', chave_ro_id='$RO_ID', chave_ro_segredo='$RO_SEG', atualizado_em=now() WHERE bucket_alias='$ALIAS'" >/dev/null
    echo "chaves novas de $ALIAS gravadas em plat.arquivo_bucket (rw ${RW_ID:0:8}…, ro ${RO_ID:0:8}…)"
    for ANTIGA in "$RW_ANTIGA" "$RO_ANTIGA"; do
      [ -n "$ANTIGA" ] || continue
      curl -fsS -m 10 -X POST -H "Authorization: Bearer $TOKEN" "$ADMIN_URL/v2/DeleteKey?id=$ANTIGA" >/dev/null
      echo "chave anterior ${ANTIGA:0:8}… apagada do Garage"
    done
    echo "== PLAT_GARAGE_S3 de '$SLUG' rotacionado em $((SECONDS - INICIO)) s, sem reinício e sem janela de indisponibilidade"
    exit 0
    ;;
  *)
    echo "segredo desconhecido: $NOME (admitidos: PLAT_SECRET, PLAT_DSN_WORKER, PLAT_DSN, PLAT_GARAGE_ADMIN_TOKEN, PLAT_GARAGE_S3 <slug>)" >&2
    exit 1
    ;;
esac
chmod 600 "$ARQUIVO"; chown root:root "$ARQUIVO"

for PAR in "${UNIDADES[@]}"; do
  UNIDADE=${PAR%%:*}; PORTA=${PAR##*:}
  echo "== reiniciando $UNIDADE (uma unidade de cada vez; a baixa é o tempo deste restart)"
  systemctl restart "$UNIDADE"
  for i in $(seq 1 30); do
    if curl -fsS -m 2 "http://127.0.0.1:$PORTA/saude" >/dev/null 2>&1; then
      echo "$UNIDADE respondeu 200 em /saude em ${i} s"
      break
    fi
    if [ "$i" -eq 30 ]; then
      echo "$UNIDADE não respondeu 200 em /saude em 30 s após a rotação:" >&2
      journalctl -u "$UNIDADE" -n 30 --no-pager >&2
      exit 3
    fi
    sleep 1
  done
done
if [ "$NOME" = "PLAT_GARAGE_ADMIN_TOKEN" ] && [ -n "${ANTERIORES:-}" ]; then
  while read -r VELHO; do
    [ -n "$VELHO" ] || continue
    "${GARAGE[@]}" admin-token delete --yes "$VELHO" >/dev/null 2>&1 && echo "token gerenciado anterior $VELHO apagado"
  done <<<"$ANTERIORES"
fi
echo "== $NOME rotacionado em $((SECONDS - INICIO)) s (baixa = o tempo dos restarts acima, nada além disso)"
