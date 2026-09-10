#!/usr/bin/env bash
# Confere a integridade das grades NTv2 do IBGE (item L2-17-crs-transformacoes) contra
# grades_ibge/SHA256SUMS. Chamado pelo install.sh (seção "h5"). Idempotente, sem efeito colateral no
# sistema: os .gsb já estão versionados no repositório (mesmo padrão de osrm/*.osrm) e são lidos por
# CAMINHO ABSOLUTO direto pelo pipeline PROJ (app/crs/grades.py) — "instalar" aqui é ATESTAR que o
# conteúdo é exatamente o baixado do IBGE, não copiar para outro lugar (não há PROJ_DATA compartilhado
# que esta trilha possa escrever: /usr/share/proj é fora de /home/dev/plataforma/, regra 1 do brief).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "== grades_ibge/instalar.sh: conferindo sha256 das grades NTv2 do IBGE"
if ! sha256sum -c SHA256SUMS; then
  echo "grades_ibge/instalar.sh: FALHOU — conteúdo de .gsb diverge de SHA256SUMS (grade corrompida ou trocada)" >&2
  exit 1
fi
for f in SAD69_003.GSB CA61_003.GSB CA7072_003.GSB; do
  [ -s "$f" ] || { echo "grades_ibge/instalar.sh: $f ausente ou vazio" >&2; exit 1; }
done
echo "== grades_ibge/instalar.sh: 3 grades conferidas (SAD69, Córrego Alegre 1961, Córrego Alegre 1970/72)"
