#!/usr/bin/env bash
# Orquestrador do `make homolog` (item L7-31; docs/HOMOLOGACAO.md): garante o bootstrap (schema
# plat_homolog, papéis, pg_hba), sobe API (uvicorn, :8154) e worker temporários apontando para o
# schema de homologação via variável de ambiente, roda a suíte de e2e (mesma suíte de `make e2e`,
# -m lento) contra http://127.0.0.1:8154 isoladamente, e DERRUBA os dois processos ao final —
# sucesso, falha ou Ctrl-C (trap EXIT). Nunca toca plat-api/plat-worker (portas/unidades diferentes,
# schema diferente, papéis diferentes). Serializado por flock contra qualquer outro `make check`/
# `pytest` da casa (regra de T2: dois pytest ao mesmo tempo na mesma árvore invalidam sessões de
# demo e disputam o único slot de worker).
set -euo pipefail
DIR_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR_REPO"
VAR_HOMOLOG="$DIR_REPO/var/homolog"
LOCK=/home/dev/plataforma/laco/.pytest.lock
PORTA_API=8154        # o que a suíte e o resto da casa chamam de "a API de homologação" (nginx)
PORTA_API_INTERNA=8158  # uvicorn de verdade; só o nginx de db/homolog_bootstrap.sh fala com ela —
                        # a app não serve /static/ sozinha, por isso o nginx na frente (achado do 1º turno)
export PYTHONNOUSERSITE=1

echo "== 0. memória disponível antes de subir processo novo"
free -h | sed -n '1,2p'

echo "== 1. bootstrap (idempotente)"
bash db/homolog_bootstrap.sh

# carrega var/homolog/homolog.env por cima do ambiente atual (o mesmo padrão de app/settings.py:
# valores_do_ambiente(), ambiente do processo por cima do .env)
set -a
# shellcheck disable=SC1091
source "$VAR_HOMOLOG/homolog.env"
set +a

PID_API=""
PID_WORKER=""
encerrar() {
  local codigo=$?
  echo "== derrubando API/worker de homologação (código de saída $codigo)"
  # SÓ pelo PID exato que este script guardou — nunca por padrão de linha de comando: o worker de
  # produção sobe com a MESMA linha "python -m app.jobs.worker" (só o ambiente muda), então qualquer
  # pkill -f aqui poderia matar o plat-worker de verdade. kill por PID não tem esse risco.
  [ -n "$PID_WORKER" ] && kill "$PID_WORKER" 2>/dev/null || true
  [ -n "$PID_API" ] && kill "$PID_API" 2>/dev/null || true
  wait "$PID_WORKER" 2>/dev/null || true
  wait "$PID_API" 2>/dev/null || true
  exit "$codigo"
}
trap encerrar EXIT INT TERM

echo "== 2. subindo API de homologação (uvicorn interno :$PORTA_API_INTERNA, nginx expõe :$PORTA_API)"
"$DIR_REPO/venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORTA_API_INTERNA" \
  --no-access-log >"$VAR_HOMOLOG/api.log" 2>&1 &
PID_API=$!

echo "== 3. subindo worker de homologação"
"$DIR_REPO/venv/bin/python" -m app.jobs.worker >"$VAR_HOMOLOG/worker.log" 2>&1 &
PID_WORKER=$!

echo "== 4. esperando /saude responder (até 20 s)"
ok=0
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$PORTA_API/saude" -o /dev/null 2>/dev/null; then ok=1; break; fi
  sleep 0.5
done
if [ "$ok" != 1 ]; then
  echo "API de homologação não respondeu em 20 s; tail do log:" >&2
  tail -n 40 "$VAR_HOMOLOG/api.log" >&2 || true
  exit 1
fi
echo "API de homologação no ar (pid $PID_API); worker pid $PID_WORKER"

echo "== 5. suíte de e2e (-m lento) contra http://127.0.0.1:$PORTA_API, sob flock $LOCK"
flock "$LOCK" "$DIR_REPO/venv/bin/pytest" -m lento --base-url "http://127.0.0.1:$PORTA_API"
