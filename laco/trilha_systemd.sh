#!/bin/bash
# Gera e instala 3 unidades systemd (api/worker/martin) para uma trilha, a partir do .env que
# trilha_ambiente.sh já escreve (item "unidades systemd de trilha", 10/09/2026 — antes disto tudo
# rodava solto com nohup+PID em /tmp e um reboot derrubava o ar sem religar sozinho, achado registrado
# em laco/handoffs/T8/LANCAMENTO.md).
#
# Molde: deploy/plat-{api,worker,martin}.service (produção, unidade ÚNICA plat-api/plat-worker/
# plat-martin — NUNCA tocar essas). Este gerador cria a MESMA forma (User=dev, Restart=on-failure,
# MemoryMax declarado, [Install] WantedBy=multi-user.target) para N trilhas paralelas, uma porta cada.
#
# Segredo: EnvironmentFile=, NÃO LoadCredential=. O .env da trilha (laco/var/trilha/<nome>.env,
# trilha_ambiente.sh passo "e") já é 0600 dono dev — o MESMO mecanismo que o nohup usava até hoje
# (`set -a; source .env; set +a; exec ...`). Trocar para LoadCredential exigiria copiar cada segredo de
# trilha para /etc/plat/segredos/<nome>/ como root, TODA vez que trilha_ambiente.sh gira a senha — mais
# um passo privilegiado para uma pista que nasce e morre em horas. E o ganho de isolamento não existe
# nesta máquina: docs/SEGURANCA.md §1 já mede que LoadCredential só isola por USUÁRIO do sistema, e
# aqui TODO produto roda como `dev` — outro processo de trilha rodando como dev já lê o
# CREDENTIALS_DIRECTORY de LoadCredential de qualquer outra unidade se souber o caminho, então a troca
# não fecharia nenhuma fresta de verdade, só trocaria um tipo de trabalho por outro. plat-api/plat-worker/
# plat-martin (produção) CONTINUAM em LoadCredential — não mexemos neles.
#
# uso:
#   trilha_systemd.sh <nome> --api PORTA --worker PORTA --martin PORTA [--worktree DIR] \
#                      [--martin-bin CAMINHO] [--titiler PORTA] [--sem-instalar]
#   trilha_systemd.sh <nome>                       # reusa as portas já gravadas em
#                                                   # laco/var/trilha/<nome>.portas.env (regenerar)
#
# saída: escreve/instala /etc/systemd/system/plat-<nome>-{api,worker,martin}.service, faz
# `daemon-reload`. NÃO dá enable/start sozinho — isso é um passo separado e deliberado (ver README).
set -euo pipefail

LACO=/home/dev/plataforma/laco
VAR="$LACO/var/trilha"
T=${1:?"uso: trilha_systemd.sh <nome> [--api PORTA --worker PORTA --martin PORTA] [--worktree DIR] [--martin-bin CAMINHO] [--titiler PORTA] [--sem-instalar]"}
shift || true

PORTAS_ENV="$VAR/$T.portas.env"
API=""; WORKER=""; MARTIN=""; WORKTREE=""; MARTIN_BIN=""; TITILER="8131"; INSTALAR=1
while [ $# -gt 0 ]; do
  case "$1" in
    --api) API="$2"; shift 2;;
    --worker) WORKER="$2"; shift 2;;
    --martin) MARTIN="$2"; shift 2;;
    --worktree) WORKTREE="$2"; shift 2;;
    --martin-bin) MARTIN_BIN="$2"; shift 2;;
    --titiler) TITILER="$2"; shift 2;;
    --sem-instalar) INSTALAR=0; shift;;
    *) echo "opção desconhecida: $1" >&2; exit 2;;
  esac
done

# portas: se não vieram no argumento, reusa o que já foi gravado (regeneração idempotente); se nunca
# houve registro, para com uma mensagem clara em vez de adivinhar porta e colidir com outra trilha.
if [ -f "$PORTAS_ENV" ]; then . "$PORTAS_ENV"; fi
API="${API:-${PLAT_TRILHA_PORTA_API:-}}"
WORKER="${WORKER:-${PLAT_TRILHA_PORTA_WORKER:-}}"
MARTIN="${MARTIN:-${PLAT_TRILHA_PORTA_MARTIN:-}}"
[ -n "$API" ] && [ -n "$WORKER" ] || {
  echo "faltam portas para a trilha '$T' e não há $PORTAS_ENV — primeira vez, informe --api --worker --martin" >&2
  exit 2
}

ENVF="$VAR/$T.env"
[ -f "$ENVF" ] || { echo "sem $ENVF — rode antes: laco/trilha_ambiente.sh $T" >&2; exit 2; }

# worktree: mesma lógica de FONTE em trilha_ambiente.sh (worktree do mesmo nome, senão o repo principal)
if [ -z "$WORKTREE" ]; then
  if [ -d "/home/dev/plataforma/wt/$T" ]; then WORKTREE="/home/dev/plataforma/wt/$T"
  else WORKTREE="/home/dev/plataforma/enterprise"; fi
fi
[ -x "$WORKTREE/venv/bin/python" ] || { echo "sem venv em $WORKTREE/venv/bin/python" >&2; exit 2; }
# (10/09) Nem toda trilha serve tile vetorial: a do motor multicritério (il301gtelam) não tem
# deploy/martin.yaml e não precisa de Martin. Sem esta saída, a trilha inteira ficava sem unidade
# nenhuma por causa de um componente que ela não usa — e continuava solta, morrendo no reboot.
COM_MARTIN=1
[ -f "$WORKTREE/deploy/martin.yaml" ] || { COM_MARTIN=0; echo "sem deploy/martin.yaml: gerando só api e worker" >&2; }

# binário do Martin: bin/ é gitignored (deploy/martin_instalar.sh), raramente existe em toda trilha —
# aceita override e cai para o binário já instalado que as trilhas de hoje compartilham.
if [ "$COM_MARTIN" = 1 ] && [ -z "$MARTIN_BIN" ]; then
  if [ -x "$WORKTREE/bin/martin" ]; then MARTIN_BIN="$WORKTREE/bin/martin"
  elif [ -x /home/dev/plataforma/wt/l201mapa/bin/martin ]; then MARTIN_BIN=/home/dev/plataforma/wt/l201mapa/bin/martin
  else echo "sem binário do Martin; informe --martin-bin" >&2; exit 2; fi
fi
[ "$COM_MARTIN" = 0 ] || [ -x "$MARTIN_BIN" ] || { echo "martin_bin não executável: $MARTIN_BIN" >&2; exit 2; }

# grava/atualiza o registro de portas (não é segredo; fica junto do resto da trilha em laco/var/trilha/)
cat > "$PORTAS_ENV" <<EOF
PLAT_TRILHA_PORTA_API=$API
PLAT_TRILHA_PORTA_WORKER=$WORKER
PLAT_TRILHA_PORTA_MARTIN=$MARTIN
PLAT_TRILHA_WORKTREE=$WORKTREE
PLAT_TRILHA_MARTIN_BIN=$MARTIN_BIN
PLAT_TRILHA_TITILER=$TITILER
EOF
chmod 600 "$PORTAS_ENV"

# config do Martin desta trilha, PERSISTENTE (o /tmp/martin-<nome>.yaml de hoje some no reboot) —
# copiado do molde do worktree, só a porta muda; nenhum segredo aqui (igual ao molde: ${PLAT_DSN_LEITOR}
# vem do ambiente do processo, que a unidade injeta por EnvironmentFile).
MARTIN_YAML="$VAR/$T.martin.yaml"
if [ "$COM_MARTIN" = 1 ]; then
  sed "s/^listen_addresses:.*/listen_addresses: '127.0.0.1:$MARTIN'/" "$WORKTREE/deploy/martin.yaml" > "$MARTIN_YAML"
fi

UNIDADES_DIR=/etc/systemd/system
API_UNIT="plat-$T-api.service"
WORKER_UNIT="plat-$T-worker.service"
MARTIN_UNIT="plat-$T-martin.service"
VIGIA_UNIT="plat-$T-martin-vigia.service"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/$API_UNIT" <<EOF
# Gerado por laco/trilha_systemd.sh — NÃO editar à mão, regenerar:
#   laco/trilha_systemd.sh $T --api $API --worker $WORKER --martin $MARTIN
# Molde: deploy/plat-api.service (produção). Diferença: EnvironmentFile em vez de LoadCredential — ver
# cabeçalho do gerador para o porquê.
[Unit]
Description=plat trilha $T — API (FastAPI :$API). Interno. Análise / beta privado.
After=postgresql@16-main.service network-online.target
Wants=postgresql@16-main.service
Requires=network-online.target

[Service]
Type=simple
User=dev
Group=dev
WorkingDirectory=$WORKTREE
Environment=PYTHONNOUSERSITE=1
Environment=PLAT_MARTIN_URL=http://127.0.0.1:$MARTIN
Environment=PLAT_WORKER_URL=http://127.0.0.1:$WORKER
Environment=PLAT_TITILER_URL=http://127.0.0.1:$TITILER
EnvironmentFile=$ENVF
ExecStart=$WORKTREE/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $API --workers 2 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log
Restart=on-failure
RestartSec=3
MemoryHigh=896M
MemoryMax=1200M
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > "$TMP/$WORKER_UNIT" <<EOF
# Gerado por laco/trilha_systemd.sh — NÃO editar à mão, regenerar:
#   laco/trilha_systemd.sh $T --api $API --worker $WORKER --martin $MARTIN
# Molde: deploy/plat-worker.service (produção). Diferença: EnvironmentFile em vez de LoadCredential.
[Unit]
Description=plat trilha $T — worker da fila de jobs (:$WORKER). Interno. Análise / beta privado.
After=postgresql@16-main.service network-online.target plat-$T-api.service
Wants=postgresql@16-main.service
Requires=network-online.target

[Service]
Type=simple
User=dev
Group=dev
WorkingDirectory=$WORKTREE
Environment=PYTHONNOUSERSITE=1
Environment=PLAT_MARTIN_URL=http://127.0.0.1:$MARTIN
Environment=PLAT_WORKER_URL=http://127.0.0.1:$WORKER
Environment=PLAT_TITILER_URL=http://127.0.0.1:$TITILER
EnvironmentFile=$ENVF
ExecStart=$WORKTREE/venv/bin/python -m app.jobs.worker
# sem job o worker só termina por sinal: qualquer saída é anômala (mesma regra do molde de produção)
Restart=always
RestartSec=3
TimeoutStopSec=40
KillMode=mixed
OOMPolicy=continue
MemoryHigh=1024M
MemoryMax=1536M
Nice=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > "$TMP/$MARTIN_UNIT" <<EOF
# Gerado por laco/trilha_systemd.sh — NÃO editar à mão, regenerar:
#   laco/trilha_systemd.sh $T --api $API --worker $WORKER --martin $MARTIN
# Molde: deploy/plat-martin.service (produção). Config em $MARTIN_YAML (persistente; o /tmp/martin-*.yaml
# antigo não sobrevive a reboot). PLAT_DSN_LEITOR vem do EnvironmentFile (trilha_ambiente.sh passo "e"),
# igual ao que o Martin já lia por variável de ambiente antes, sem LoadCredential/wrapper de shell.
[Unit]
Description=plat trilha $T — servidor de tiles vetoriais Martin (:$MARTIN). Interno. Análise / beta privado.
After=postgresql@16-main.service network-online.target
Requires=postgresql@16-main.service network-online.target

[Service]
Type=simple
User=dev
Group=dev
WorkingDirectory=$WORKTREE
EnvironmentFile=$ENVF
ExecStart=$MARTIN_BIN --config $MARTIN_YAML
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
EOF

# 4ª unidade: vigia do Martin (martin 1.15 não redescobre função de tile nova sem reiniciar — achado
# 10/09/2026, deploy/martin_vigia.sh). Sem isto, uma camada publicada depois do boot da unidade Martin
# fica 502 até alguém religar à mão; a irmã nohup deste vigia (que existia antes) morre no reboot igual
# a tudo o resto, então a unidade abaixo é parte do mesmo conserto, não um extra separado.
cat > "$TMP/$VIGIA_UNIT" <<EOF
# Gerado por laco/trilha_systemd.sh — NÃO editar à mão, regenerar:
#   laco/trilha_systemd.sh $T --api $API --worker $WORKER --martin $MARTIN
# deploy/martin_vigia_systemd.sh religa $MARTIN_UNIT (via systemctl, dev tem sudo NOPASSWD) quando o
# número de funções de tile muda ou a unidade não está ativa — molde novo, não existia antes desta trilha.
[Unit]
Description=plat trilha $T — vigia do Martin (religa quando função de tile nova aparece)
After=$MARTIN_UNIT
Requires=$MARTIN_UNIT

[Service]
Type=simple
User=dev
Group=dev
WorkingDirectory=$WORKTREE
EnvironmentFile=$ENVF
ExecStart=/usr/bin/bash $WORKTREE/deploy/martin_vigia_systemd.sh $MARTIN_UNIT 10
Restart=on-failure
RestartSec=5
MemoryMax=64M
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

UNIDADES="$API_UNIT $WORKER_UNIT"
[ "$COM_MARTIN" = 1 ] && UNIDADES="$UNIDADES $MARTIN_UNIT $VIGIA_UNIT"
for f in $UNIDADES; do
  # nunca sobrescrever unidade que não é nossa (defesa contra digitar o nome errado de trilha)
  if [ -e "$UNIDADES_DIR/$f" ] && ! sudo -n grep -q "Gerado por laco/trilha_systemd.sh" "$UNIDADES_DIR/$f" 2>/dev/null; then
    echo "ERRO: $UNIDADES_DIR/$f já existe e NÃO foi gerado por este script — recuso sobrescrever" >&2
    exit 3
  fi
done

if [ "$INSTALAR" = 1 ]; then
  for f in $UNIDADES; do sudo -n install -m 0644 "$TMP/$f" "$UNIDADES_DIR/$f"; done
  sudo -n systemctl daemon-reload
  echo "instaladas: $UNIDADES (daemon-reload feito; enable/start é passo separado)"
else
  cp "$TMP/$API_UNIT" "$TMP/$WORKER_UNIT" "$TMP/$MARTIN_UNIT" "$TMP/$VIGIA_UNIT" "$VAR/"
  echo "--sem-instalar: unidades escritas em $VAR/ para conferência, nada instalado"
fi
