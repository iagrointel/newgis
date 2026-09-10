#!/usr/bin/env bash
# Publica (aprova para instalação) um pacote de release já preparado por scripts/preparar_release.sh — a
# decisão humana que aquele script deixa em aberto (item L7-15-processo-release, docs/RELEASE.md).
#
# Recusa (saída != 0) sempre que o pacote não prova, por si só, que passou pela linha inteira:
#   4  assinatura não confere (scripts/verificar_pacote.sh, item L7-16 — pacote alterado, renomeado, ou
#      chave desconhecida nesta instalação)
#   5  sem RELEASE_MANIFEST.json dentro do pacote (não foi gerado por preparar_release.sh)
#   6  manifesto presente mas sem PROVA de teste: comando substituído, código de saída != 0, ou nenhum
#      teste contado na saída do comando
#   7  versão repetida ou menor que a última já publicada nesta instalação (repetição/regressão)
#
# ⛔ ENDURECIDO em 06/09/2026 (ataque adversarial ao grupo G6, laudo em
# laco/handoffs/T3/ataque-g6-ADVERSARIO.md), três buracos medidos:
#   a. `PLAT_VERIFICAR_SCRIPT=/bin/true` desligava a verificação de assinatura. A variável NÃO EXISTE
#      mais: o verificador é sempre o scripts/verificar_pacote.sh ao lado deste arquivo.
#   b. o manifesto dizia "make_check": "passou" como texto fixo. Agora este script exige a EVIDÊNCIA que
#      preparar_release.sh grava (comando canônico, código 0, testes contados > 0) e recusa o resto.
#   c. repetição e regressão de versão eram aceitas, sem registro nenhum do que já tinha entrado. Agora
#      cada publicação aprovada é anexada a var/releases_publicados.jsonl e a versão tem de ser
#      estritamente maior que a última.
#
# Uso: bash scripts/publicar_release.sh <pacote.tar.gz>
set -euo pipefail
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
APP_DIR=${APP_DIR:-$(cd "$AQUI/.." && pwd)}
PACOTE=${1:?"uso: bash scripts/publicar_release.sh <pacote.tar.gz>"}
[ -f "$PACOTE" ] || { echo "recusado: pacote não existe: $PACOTE" >&2; exit 1; }

REGISTRO="$APP_DIR/var/releases_publicados.jsonl"
CMD_CHECK_CANONICO="make check"
CMD_HOMOLOG_CANONICO="make homolog"

if ! bash "$AQUI/verificar_pacote.sh" "$PACOTE"; then
  echo "RECUSADO: assinatura não confere para $PACOTE (o pacote pode ter sido alterado ou renomeado, ou a" >&2
  echo "chave que assinou não é confiável nesta instalação — deploy/chaves_publicas_release.txt)" >&2
  exit 4
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
if ! tar -xzf "$PACOTE" -C "$TMP" RELEASE_MANIFEST.json 2>/dev/null; then
  echo "RECUSADO: $PACOTE não tem RELEASE_MANIFEST.json — não passou por scripts/preparar_release.sh" >&2
  echo "(assinatura válida sozinha não basta: sem o manifesto não há prova de que rodou make check/homolog)" >&2
  exit 5
fi

# A prova é lida do manifesto que viaja DENTRO do arquivo assinado. Um manifesto de formato antigo
# (texto fixo "passou") não prova nada e é recusado junto.
VEREDITO=$(env PYTHONNOUSERSITE=1 python3 - "$TMP/RELEASE_MANIFEST.json" "$CMD_CHECK_CANONICO" "$CMD_HOMOLOG_CANONICO" <<'PY'
import json
import sys

caminho, canonico_check, canonico_homolog = sys.argv[1], sys.argv[2], sys.argv[3]
canonicos = {"check": canonico_check, "homolog": canonico_homolog}
try:
    m = json.load(open(caminho))
except Exception as e:  # noqa: BLE001
    print(f"6|manifesto ilegível ({e})")
    raise SystemExit
if m.get("formato") != "plat-release-manifest-2":
    print(
        "6|manifesto no formato antigo (%r): os campos make_check/make_homolog eram texto fixo, não "
        "prova. Corte a release de novo com scripts/preparar_release.sh." % (m.get("formato"),)
    )
    raise SystemExit
versao = str(m.get("versao") or "")
etapas = m.get("etapas") or {}
problemas = []
for nome, canonico in canonicos.items():
    e = etapas.get(nome) or {}
    if e.get("comando") != canonico:
        problemas.append(f"{nome}: comando executado foi {e.get('comando')!r}, não {canonico!r}")
        continue
    if e.get("codigo_saida") != 0:
        problemas.append(f"{nome}: código de saída {e.get('codigo_saida')}")
    if not isinstance(e.get("testes_contados"), int) or e["testes_contados"] < 1:
        problemas.append(f"{nome}: nenhum teste contado na saída ({e.get('testes_contados')})")
if problemas:
    print("6|" + "; ".join(problemas))
    raise SystemExit
if not versao:
    print("6|manifesto sem versão")
    raise SystemExit
print(f"0|{versao}")
PY
)
CODIGO=${VEREDITO%%|*}
DETALHE=${VEREDITO#*|}
if [ "$CODIGO" != "0" ]; then
  echo "RECUSADO: RELEASE_MANIFEST.json não prova que a linha de teste rodou — $DETALHE ($PACOTE)" >&2
  exit "$CODIGO"
fi
VERSAO="$DETALHE"

# Piso de versão: a última já publicada nesta instalação. Recusa repetição e regressão.
ANTERIOR=$(env PYTHONNOUSERSITE=1 python3 - "$REGISTRO" <<'PY'
import json
import sys
from pathlib import Path

caminho = Path(sys.argv[1])
maior = ""
if caminho.exists():
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            v = json.loads(linha).get("versao") or ""
        except json.JSONDecodeError:
            continue
        chave = tuple(int(x) for x in v.split(".")) if v.count(".") == 2 and all(
            p.isdigit() for p in v.split(".")
        ) else None
        if chave and (not maior or chave > tuple(int(x) for x in maior.split("."))):
            maior = v
print(maior)
PY
)
if [ -n "$ANTERIOR" ]; then
  MAIOR=$(printf '%s\n%s\n' "$ANTERIOR" "$VERSAO" | sort -V | tail -1)
  if [ "$VERSAO" = "$ANTERIOR" ] || [ "$MAIOR" != "$VERSAO" ]; then
    echo "RECUSADO: versão $VERSAO não é maior que a última publicada ($ANTERIOR) — repetição de pacote e" >&2
    echo "regressão de versão são as duas formas de reinstalar um release velho já corrigido. Registro:" >&2
    echo "$REGISTRO" >&2
    exit 7
  fi
fi

SHA=$(sha256sum "$PACOTE" | cut -d' ' -f1)
mkdir -p "$(dirname "$REGISTRO")"
env PYTHONNOUSERSITE=1 python3 - "$REGISTRO" "$VERSAO" "$SHA" "$PACOTE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(id -un)" <<'PY'
import json
import sys

registro, versao, sha, pacote, quando, quem = sys.argv[1:7]
with open(registro, "a", encoding="utf-8") as f:
    f.write(
        json.dumps(
            {"versao": versao, "sha256": sha, "pacote": pacote, "quando": quando, "por": quem},
            ensure_ascii=False,
        )
        + "\n"
    )
PY
echo "aprovado para produção: $PACOTE (versão=$VERSAO sha256=$SHA)"
echo "registrado em $REGISTRO — a partir daqui esta versão e qualquer anterior são recusadas"
echo "próximo passo humano: extrair sobre o diretório de produção e rodar install.sh <dominio> [porta] de lá"
echo "(este script não roda install.sh sozinho: instalar em produção de verdade é sempre decisão humana"
echo "explícita, e install.sh exige root/domínio que este comando não tem contexto para escolher por você)"
