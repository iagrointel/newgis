#!/bin/bash
# pytest do worktree l56 com teto de memoria RESIDENTE por cgroup (regra 18/09) e o ambiente da
# trilha carregado DENTRO do escopo (sudo descarta o ambiente do chamador). Nenhum segredo impresso.
set -uo pipefail
W=/home/dev/plataforma/wt/l56
T=${TRILHA:-seg}
D=/home/dev/plataforma/laco/vivo/vagas; mkdir -p "$D"
ARGS=$(printf '%q ' "$@")
t0=$SECONDS
while :; do
  for i in 1 2 3 4 5 6; do
    exec {fd}>"$D/$i.lock"
    if flock -n "$fd"; then
      sudo systemd-run --scope --uid="$(id -u)" --gid="$(id -g)" -q \
        -p MemoryMax="${PLAT_TESTE_RSS:-4G}" -p MemorySwapMax=0 \
        /bin/bash -c "cd $W; set -a; . /home/dev/plataforma/laco/var/trilha/$T.env; set +a; export OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 PLAT_TESTE_EM_CGROUP=1; timeout ${PLAT_TESTE_TIMEOUT:-900} venv/bin/pytest $ARGS -p no:cacheprovider"
      c=$?; flock -u "$fd"; exec {fd}>&-; exit $c
    fi
    exec {fd}>&-
  done
  [ $((SECONDS-t0)) -ge 1800 ] && { echo "[teste] sem vaga" >&2; exit 75; }
  sleep $((RANDOM % 5 + 3))
done
