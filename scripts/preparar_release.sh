#!/usr/bin/env bash
# Processo de release (item L7-15-processo-release; docs/RELEASE.md). Automatiza o que dá sem decisão
# humana e PARA no primeiro erro: (1) valida X.Y.Z como semver 2.0.0; (2) gera o rascunho de changelog
# (keep-a-changelog) do `git log` desde a última etiqueta — scripts/gerar_changelog_release.py, NUNCA edita
# CHANGELOG.md sozinho; (3) `make check`; (4) `make homolog`; (5) empacota a árvore de produção num tar
# determinístico COM um RELEASE_MANIFEST.json dentro; (6) assina com scripts/assinar_pacote.sh; (7) cria a
# etiqueta ASSINADA vX.Y.Z e confere que CHANGELOG.md tem a seção correspondente; e PARA — falta só a
# decisão humana de publicar, com scripts/publicar_release.sh.
#
# ⛔ ENDURECIDO em 06/09/2026 (ataque adversarial ao grupo G6, laudo em
# laco/handoffs/T3/ataque-g6-ADVERSARIO.md). O que mudou:
#
#   a. O MANIFESTO PASSOU A REGISTRAR O QUE REALMENTE RODOU. Antes, os campos "make_check" e
#      "make_homolog" eram o texto fixo "passou", escrito sem olhar resultado nenhum — bastava
#      PLAT_RELEASE_CHECK_CMD=true para um pacote que nunca rodou teste sair "aprovado para produção".
#      Agora cada etapa grava comando executado, código de saída, número de testes contados na saída,
#      duração e o sha256 do log; o log fica em var/releases/<versao>.<etapa>.log. Substituir o comando
#      continua possível (os testes deste repositório dependem disso), mas fica ESCRITO no manifesto, e
#      scripts/publicar_release.sh recusa qualquer pacote cujo manifesto não mostre o comando canônico
#      com código 0 e pelo menos um teste contado.
#   b. O arquivo VERSAO empacotado passa a ser o da versão que está sendo cortada (antes o pacote 9.9.9
#      viajava com VERSAO=0.1.0 dentro).
#   c. A etiqueta é ASSINADA (`git tag -s`, assinatura SSH derivada da MESMA chave Ed25519 do release), e
#      var/releases/allowed_signers sai da lista de confiança do produto — `git tag -v` passa a conferir
#      de verdade. Antes era `git tag -a` e `git tag -v` respondia "no signature found".
#
# Uso: bash scripts/preparar_release.sh X.Y.Z [--hotfix]
#   --hotfix   exige rodar no ramo hotfix/X.Y.Z (recusa em qualquer outro ramo)
#
# Variáveis:
#   APP_DIR                    árvore a empacotar (padrão: a raiz deste repositório)
#   PLAT_RELEASE_CHECK_CMD     comando no lugar de "make check"   (padrão: "make check")
#   PLAT_RELEASE_HOMOLOG_CMD   comando no lugar de "make homolog" (padrão: "make homolog")
#   PLAT_PACOTE_ITENS          lista de itens a empacotar, separados por espaço (padrão: ver ITENS)
# Não existe mais PLAT_ASSINAR_SCRIPT: a assinatura é sempre scripts/assinar_pacote.sh ao lado deste.
set -euo pipefail
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
APP_DIR=${APP_DIR:-$(cd "$AQUI/.." && pwd)}
VERSAO=${1:?"uso: bash scripts/preparar_release.sh X.Y.Z [--hotfix]"}
HOTFIX=0
for arg in "$@"; do [ "$arg" = "--hotfix" ] && HOTFIX=1; done

CMD_CHECK_PADRAO="make check"
CMD_HOMOLOG_PADRAO="make homolog"

SEMVER_RE='^[0-9]+\.[0-9]+\.[0-9]+$'
if ! [[ "$VERSAO" =~ $SEMVER_RE ]]; then
  echo "recusado: versão precisa ser semver 2.0.0 (MAJOR.MINOR.PATCH): '$VERSAO'" >&2
  exit 1
fi

cd "$APP_DIR"

if [ "$HOTFIX" = 1 ]; then
  RAMO=$(git rev-parse --abbrev-ref HEAD)
  if [ "$RAMO" != "hotfix/$VERSAO" ]; then
    echo "recusado: --hotfix exige estar no ramo hotfix/$VERSAO (ramo atual: $RAMO)" >&2
    exit 1
  fi
fi

TAG="v$VERSAO"
if [ -n "$(git tag -l "$TAG")" ]; then
  echo "recusado: etiqueta $TAG já existe" >&2
  exit 1
fi

DIR_SAIDA="$APP_DIR/var/releases"
mkdir -p "$DIR_SAIDA"
PY=(python3)

# Roda uma etapa registrando a EVIDÊNCIA: comando, código de saída, testes contados na saída, duração e
# sha256 do log. Escreve o resumo em $DIR_SAIDA/<versao>.<etapa>.json; nunca inventa "passou".
rodar_etapa() {
  local etapa=$1 comando=$2 padrao=$3
  local log="$DIR_SAIDA/$VERSAO.$etapa.log"
  local inicio fim codigo testes sha
  inicio=$(date +%s)
  set +e
  (cd "$APP_DIR" && eval "$comando") 2>&1 | tee "$log"
  codigo=${PIPESTATUS[0]}
  set -e
  fim=$(date +%s)
  # contagem de testes: soma dos "N passed"/"N passaram" que o pytest imprime no resumo final
  testes=$(grep -oE '[0-9]+ (passed|passaram)' "$log" 2>/dev/null | grep -oE '^[0-9]+' | awk '{s+=$1} END {print s+0}')
  [ -n "$testes" ] || testes=0
  sha=$(sha256sum "$log" | cut -d' ' -f1)
  "${PY[@]}" - "$DIR_SAIDA/$VERSAO.$etapa.json" "$comando" "$padrao" "$codigo" "$testes" "$((fim - inicio))" "$sha" "$log" <<'PY'
import json
import sys

destino, comando, padrao, codigo, testes, duracao, sha, log = sys.argv[1:9]
json.dump(
    {
        "comando": comando,
        "comando_canonico": padrao,
        "substituido": comando != padrao,
        "codigo_saida": int(codigo),
        "testes_contados": int(testes),
        "duracao_s": int(duracao),
        "log": log,
        "log_sha256": sha,
    },
    open(destino, "w"),
    ensure_ascii=False,
    indent=1,
)
PY
  return "$codigo"
}

echo "== 1/7 validação de versão: $VERSAO ($([ "$HOTFIX" = 1 ] && echo hotfix || echo normal))"

echo "== 2/7 rascunho de changelog"
ULTIMA_TAG=$(git describe --tags --abbrev=0 2>/dev/null || true)
INTERVALO="HEAD"
[ -n "$ULTIMA_TAG" ] && INTERVALO="$ULTIMA_TAG..HEAD"
CHANGELOG_DRAFT="$DIR_SAIDA/$VERSAO.changelog.md"
"${PY[@]}" "$AQUI/gerar_changelog_release.py" \
  --repo "$APP_DIR" --versao "$VERSAO" --range "$INTERVALO" --saida "$CHANGELOG_DRAFT" > /dev/null
echo "rascunho: $CHANGELOG_DRAFT (desde ${ULTIMA_TAG:-o início})"

echo "== 3/7 $CMD_CHECK_PADRAO (escopo verde)"
CMD_CHECK=${PLAT_RELEASE_CHECK_CMD:-$CMD_CHECK_PADRAO}
[ "$CMD_CHECK" = "$CMD_CHECK_PADRAO" ] || echo "AVISO: comando de teste SUBSTITUÍDO por '$CMD_CHECK' — o" \
  "manifesto vai registrar isso e scripts/publicar_release.sh vai RECUSAR o pacote" >&2
if ! rodar_etapa check "$CMD_CHECK" "$CMD_CHECK_PADRAO"; then
  echo "RELEASE RECUSADA: '$CMD_CHECK' falhou — nada foi empacotado nem assinado" >&2
  exit 2
fi

echo "== 4/7 $CMD_HOMOLOG_PADRAO"
CMD_HOMOLOG=${PLAT_RELEASE_HOMOLOG_CMD:-$CMD_HOMOLOG_PADRAO}
[ "$CMD_HOMOLOG" = "$CMD_HOMOLOG_PADRAO" ] || echo "AVISO: comando de homologação SUBSTITUÍDO por" \
  "'$CMD_HOMOLOG' — o manifesto vai registrar isso e scripts/publicar_release.sh vai RECUSAR o pacote" >&2
if ! rodar_etapa homolog "$CMD_HOMOLOG" "$CMD_HOMOLOG_PADRAO"; then
  echo "RELEASE RECUSADA: '$CMD_HOMOLOG' falhou — nada foi empacotado nem assinado" >&2
  exit 3
fi

echo "== 5/7 empacotar"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
read -r -a ITENS <<< "${PLAT_PACOTE_ITENS:-app web db deploy docs install.sh Makefile requirements.txt VERSAO}"
for item in "${ITENS[@]}"; do
  [ -e "$APP_DIR/$item" ] && cp -a "$APP_DIR/$item" "$STAGE/$item"
done
# o pacote carrega a versão que está sendo cortada, não a que estava no disco (achado 9 do adversário:
# o pacote 9.9.9 viajava com VERSAO=0.1.0 dentro)
printf '%s\n' "$VERSAO" > "$STAGE/VERSAO"
COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "sem-git")
QUANDO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
"${PY[@]}" - "$STAGE/RELEASE_MANIFEST.json" "$VERSAO" "$COMMIT" "$QUANDO" \
  "$DIR_SAIDA/$VERSAO.check.json" "$DIR_SAIDA/$VERSAO.homolog.json" <<'PY'
import json
import sys

destino, versao, commit, quando, check, homolog = sys.argv[1:7]
manifesto = {
    "formato": "plat-release-manifest-2",
    "versao": versao,
    "commit": commit,
    "quando": quando,
    "etapas": {"check": json.load(open(check)), "homolog": json.load(open(homolog))},
}
json.dump(manifesto, open(destino, "w"), ensure_ascii=False, indent=2)
PY
PACOTE="$DIR_SAIDA/plat-$VERSAO.tar.gz"
rm -f "$PACOTE"
# --transform tira o prefixo './' que '-C "$STAGE" .' deixaria (senão publicar_release.sh não acha
# RELEASE_MANIFEST.json pelo nome exato dentro do tar)
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner --transform='s,^\./,,' -czf "$PACOTE" -C "$STAGE" .
SHA=$(sha256sum "$PACOTE" | cut -d' ' -f1)
echo "pacote: $PACOTE (sha256=$SHA)"

echo "== 6/7 assinar"
bash "$AQUI/assinar_pacote.sh" "$PACOTE" --versao "$VERSAO"

echo "== 7/7 etiqueta git ASSINADA + conferência changelog×etiqueta"
# A etiqueta é assinada com a MESMA chave Ed25519 do pacote, exportada em formato OpenSSH; o
# allowed_signers sai da lista de confiança do produto, então `git tag -v` confere contra a mesma âncora
# que `verificar_pacote.sh`. Sem isso a etiqueta era só anotada e não provava origem nenhuma.
if [ -n "${PLAT_CHAVE_PRIVADA:-}" ]; then
  CHAVE_PRIVADA="$PLAT_CHAVE_PRIVADA"
elif [ "$(id -u)" -eq 0 ]; then
  CHAVE_PRIVADA=/etc/plat/chaves/release_ed25519_priv.pem
else
  CHAVE_PRIVADA="$HOME/.config/plat/chaves/release_ed25519_priv.pem"
fi
CONFIAVEIS_ETIQUETA="$AQUI/../deploy/chaves_publicas_release.txt"
AMBIENTE=$(printf '%s' "${PLAT_AMBIENTE:-}" | tr '[:upper:]' '[:lower:]')
case "$AMBIENTE" in
  dev|teste|test|homolog|homologacao)
    [ -n "${PLAT_CHAVES_CONFIAVEIS:-}" ] && CONFIAVEIS_ETIQUETA="$PLAT_CHAVES_CONFIAVEIS" ;;
esac
CHAVE_SSH="$DIR_SAIDA/release_ssh_$VERSAO"
ASSINANTES="$DIR_SAIDA/allowed_signers"
VENV_PY="$AQUI/../venv/bin/python"
[ -x "$VENV_PY" ] || VENV_PY=python3
rm -f "$CHAVE_SSH" "$CHAVE_SSH.pub"
if ! env PYTHONNOUSERSITE=1 "$VENV_PY" "$AQUI/plat_assinatura.py" exportar-ssh \
      --chave-privada "$CHAVE_PRIVADA" --saida "$CHAVE_SSH" > /dev/null; then
  echo "RELEASE RECUSADA: não consegui exportar a chave de release para assinar a etiqueta" >&2
  exit 4
fi
if ! env PYTHONNOUSERSITE=1 "$VENV_PY" "$AQUI/plat_assinatura.py" allowed-signers \
      --confiaveis "$CONFIAVEIS_ETIQUETA" --saida "$ASSINANTES" > /dev/null; then
  echo "RELEASE RECUSADA: lista de confiança sem chave — a etiqueta não teria contra o que ser conferida" >&2
  exit 4
fi
git config gpg.format ssh
git config user.signingkey "$CHAVE_SSH"
git config gpg.ssh.allowedSignersFile "$ASSINANTES"
if ! git tag -s "$TAG" -m "release $VERSAO"; then
  echo "RELEASE RECUSADA: git tag -s falhou (etiqueta não assinada não vale como release)" >&2
  exit 4
fi
if ! git tag -v "$TAG" > /dev/null 2>&1; then
  git tag -d "$TAG" > /dev/null 2>&1 || true
  echo "RELEASE RECUSADA: a etiqueta $TAG não se verifica contra $ASSINANTES (etiqueta apagada)" >&2
  exit 4
fi
if ! bash "$AQUI/conferir_changelog_releases.sh" > /dev/null 2>&1; then
  echo "AVISO: $TAG ainda não tem seção em CHANGELOG.md — cole $CHANGELOG_DRAFT lá antes de publicar" >&2
fi

echo
echo "PRONTO — pacote assinado com este sha: $SHA"
echo "Evidência gravada: $DIR_SAIDA/$VERSAO.check.json e $DIR_SAIDA/$VERSAO.homolog.json (comando, código"
echo "de saída, testes contados, sha256 do log). O manifesto dentro do pacote carrega os mesmos dados."
echo "Falta a decisão humana: (1) revisar $CHANGELOG_DRAFT e colar em CHANGELOG.md; (2) publicar com"
echo "  bash scripts/publicar_release.sh $PACOTE"
echo "(publicar_release.sh recusa pacote cujo manifesto não mostre '$CMD_CHECK_PADRAO' e"
echo "'$CMD_HOMOLOG_PADRAO' com código 0 e testes contados > 0, e recusa versão repetida ou menor que a"
echo "última publicada.)"
