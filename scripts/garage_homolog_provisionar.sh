#!/usr/bin/env bash
# Provisiona a CREDENCIAL PRÓPRIA de armazenamento de um ambiente que não é produção (item L7-31; achado 11
# do adversário no turno 3: o token admin do Garage era byte a byte o mesmo em produção e em homologação, e
# com ele o ambiente de homologação listava e lia os buckets de produção plat-demo e plat-demo2).
#
# O que faz: garante uma CHAVE S3 do Garage com permissão de criar bucket e NENHUM acesso a bucket de outro
# ambiente, e grava só ela no arquivo de ambiente indicado, apagando de lá qualquer PLAT_GARAGE_ADMIN_TOKEN.
# Bucket criado por essa chave nasce com ALIAS LOCAL dela (medido no Garage v2.3.0): não aparece no espaço de
# nomes global, nenhuma outra chave o resolve pelo nome, e a chave recebe 403 AccessDenied em qualquer bucket
# de que não seja dona.
#
# É passo de OPERADOR, não do ambiente: quem roda isto precisa do garage.toml (rpc_secret) para falar com o
# daemon. O ambiente provisionado nunca recebe esse poder — sai daqui só o par id/segredo da chave S3.
#
# Uso:  bash scripts/garage_homolog_provisionar.sh <ARQUIVO_ENV> [NOME_DA_CHAVE]
#   ARQUIVO_ENV    arquivo de ambiente a atualizar (ex.: var/homolog/homolog.env). Criado se não existir.
#   NOME_DA_CHAVE  nome da chave no Garage (padrão: homolog-plat-provisionador)
# Variáveis: GARAGE_BIN, GARAGE_CONFIG (padrões desta máquina), abaixo.
# Idempotente: rodar de novo reaproveita a chave existente e reescreve as mesmas duas linhas.
set -euo pipefail
ARQUIVO_ENV=${1:?uso: bash scripts/garage_homolog_provisionar.sh <ARQUIVO_ENV> [NOME_DA_CHAVE]}
NOME_CHAVE=${2:-homolog-plat-provisionador}
GARAGE_BIN=${GARAGE_BIN:-/home/dev/plataforma/pipeline/bin/garage}
GARAGE_CONFIG=${GARAGE_CONFIG:-/home/dev/plataforma/pipeline/garage/garage.toml}

[ -x "$GARAGE_BIN" ] || { echo "binário do garage não encontrado/executável: $GARAGE_BIN" >&2; exit 1; }
[ -r "$GARAGE_CONFIG" ] || { echo "configuração do garage ilegível: $GARAGE_CONFIG" >&2; exit 1; }
GARAGE=("$GARAGE_BIN" -c "$GARAGE_CONFIG")

if ! "${GARAGE[@]}" key info "$NOME_CHAVE" >/dev/null 2>&1; then
  "${GARAGE[@]}" key create "$NOME_CHAVE" >/dev/null
  echo "chave S3 $NOME_CHAVE criada no Garage"
else
  echo "chave S3 $NOME_CHAVE já existia (reaproveitada, segredo inalterado)"
fi
# permissão de criar bucket: é o que substitui o poder de administração; sem ela o ambiente não consegue
# provisionar o bucket do inquilino novo que a própria suíte cria (zt-*).
"${GARAGE[@]}" key allow --create-bucket "$NOME_CHAVE" >/dev/null
INFO=$("${GARAGE[@]}" key info --show-secret "$NOME_CHAVE")
CHAVE_ID=$(sed -nE 's/^Key ID:[[:space:]]+([A-Za-z0-9]+)$/\1/p' <<<"$INFO" | head -n1)
CHAVE_SEGREDO=$(sed -nE 's/^Secret key:[[:space:]]+([A-Za-z0-9]+)$/\1/p' <<<"$INFO" | head -n1)
[ -n "$CHAVE_ID" ] && [ -n "$CHAVE_SEGREDO" ] || { echo "não consegui ler id/segredo de $NOME_CHAVE em 'garage key info'" >&2; exit 1; }

# confere na hora que a chave NÃO enxerga bucket de alias global (produção e trilhas): ListBuckets do S3
# desta chave só devolve o que é dela. Prova positiva vive em tests/unit/test_isolamento_homologacao.py.
# ("Global aliases" é a 3a coluna de `garage bucket list`; linha sem alias global é bucket de alias local.)
GLOBAIS=$("${GARAGE[@]}" bucket list 2>/dev/null | awk 'NR>1 && NF>=3 {print $3}' || true)
echo "chave $NOME_CHAVE: id ${CHAVE_ID:0:8}…, pode criar bucket, dona só dos buckets que ela mesma criar"
if [ -n "$GLOBAIS" ]; then
  echo "buckets de alias global no servidor, nenhum deles acessível por esta chave: $(grep -c . <<<"$GLOBAIS")"
fi

umask 077
touch "$ARQUIVO_ENV"; chmod 600 "$ARQUIVO_ENV"
TMP=$(mktemp); trap 'rm -f "$TMP"' EXIT
grep -vE '^(PLAT_GARAGE_ADMIN_TOKEN|PLAT_GARAGE_ADMIN_URL|PLAT_GARAGE_CHAVE_ID|PLAT_GARAGE_CHAVE_SEGREDO)=' "$ARQUIVO_ENV" > "$TMP" || true
# as duas linhas VAZIAS não são enfeite: a app lê o .env da raiz do repositório ANTES do ambiente do
# processo (app/settings.py::valores_do_ambiente), e em produção esse .env é o de PRODUÇÃO. Sem declarar
# vazio aqui, o PLAT_GARAGE_ADMIN_TOKEN do .env voltaria a valer para o processo de homologação e o achado
# 11 reapareceria pela porta dos fundos. Vazio vira None em _opcional() e desliga o modo de administração.
{
  printf 'PLAT_GARAGE_ADMIN_URL=\n'
  printf 'PLAT_GARAGE_ADMIN_TOKEN=\n'
  printf 'PLAT_GARAGE_CHAVE_ID=%s\n' "$CHAVE_ID"
  printf 'PLAT_GARAGE_CHAVE_SEGREDO=%s\n' "$CHAVE_SEGREDO"
} >> "$TMP"
cat "$TMP" > "$ARQUIVO_ENV"
chmod 600 "$ARQUIVO_ENV"
echo "$ARQUIVO_ENV atualizado: sem PLAT_GARAGE_ADMIN_URL/PLAT_GARAGE_ADMIN_TOKEN, com PLAT_GARAGE_CHAVE_ID/PLAT_GARAGE_CHAVE_SEGREDO"
