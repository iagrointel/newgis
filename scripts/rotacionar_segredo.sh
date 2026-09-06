#!/usr/bin/env bash
# Rotaciona um segredo do plat sem reinstalar e sem editar unidade systemd (item L7-19-segredos-e-
# certificados; docs/SEGURANCA.md secao "segredos e certificados"). Gera valor novo, atualiza a role no
# banco quando o segredo e uma senha de banco, grava o credential (/etc/plat/segredos/<NOME>, 0600, dono
# root) e reinicia so a unidade que le aquele segredo — uma reinicializacao por vez, o tempo de baixa e o
# tempo do "systemctl restart" (poucos segundos), nunca mais.
#
# Uso: sudo bash scripts/rotacionar_segredo.sh <PLAT_SECRET|PLAT_DSN_WORKER>
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
set -euo pipefail
NOME=${1:?uso: sudo bash scripts/rotacionar_segredo.sh <PLAT_SECRET|PLAT_DSN_WORKER>}
DB=${PLAT_DB:-iagro_sat}
CRED_DIR=/etc/plat/segredos
ARQUIVO="$CRED_DIR/$NOME"
INICIO=$SECONDS

[ "$(id -u)" -eq 0 ] || { echo "rode como root: sudo bash scripts/rotacionar_segredo.sh $NOME" >&2; exit 1; }
[ -f "$ARQUIVO" ] || { echo "$ARQUIVO não existe (rode install.sh primeiro para criar o credential)" >&2; exit 1; }
PSQL=(sudo -u postgres psql -d "$DB" -X -q -v ON_ERROR_STOP=1)

case "$NOME" in
  PLAT_SECRET)
    UNIDADE=plat-api
    PORTA=$(grep -oP -- '--port \K[0-9]+' /etc/systemd/system/plat-api.service 2>/dev/null || echo 8150)
    NOVO=$(openssl rand -hex 32)
    printf '%s' "$NOVO" > "$ARQUIVO"
    echo "PLAT_SECRET novo gerado e gravado em $ARQUIVO"
    echo "aviso: URL de objeto assinada antes desta troca para de validar; totp_secret já cifrado fica"
    echo "ilegível (usuário com 2FA entra com código de recuperação e recadastra — comportamento já"
    echo "tratado em app/auth/rotas_login.py, não é uma falha nova)"
    ;;
  PLAT_DSN_WORKER)
    UNIDADE=plat-worker
    PORTA=8153
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
  *)
    echo "segredo desconhecido: $NOME (admitidos: PLAT_SECRET, PLAT_DSN_WORKER)" >&2
    exit 1
    ;;
esac
chmod 600 "$ARQUIVO"; chown root:root "$ARQUIVO"

echo "== reiniciando $UNIDADE (única reinicialização desta rotação)"
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
echo "== $NOME rotacionado em $((SECONDS - INICIO)) s (baixa = o tempo do restart acima, nada além disso)"
