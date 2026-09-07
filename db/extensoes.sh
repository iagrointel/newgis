#!/usr/bin/env bash
# Funções da lista única de extensões (item L7-01-d). Feito para ser CARREGADO (`source`), nunca
# executado: quem carrega é o install.sh e o laco/trilha_ambiente.sh. O terceiro leitor da mesma lista
# é o ensaio de restauração (app/backup/drill.py, em Python).
#
# Nenhuma função aqui escreve em /etc, em unidade do systemd nem em arquivo do repositório: o efeito
# é só `CREATE EXTENSION IF NOT EXISTS` e leitura de pg_extension. É por isso que o teste do item pode
# exercitá-las contra uma base de ensaio sem rodar o install.sh inteiro.

# plat_extensoes_lista <arquivo>  -> um nome por linha, na ordem do arquivo.
# Mesmo formato e mesmo par grep/awk de deploy/pacotes_apt.txt (install.sh seção e2).
plat_extensoes_lista() {
  local arquivo=${1:?uso: plat_extensoes_lista <arquivo>}
  [ -r "$arquivo" ] || { echo "lista de extensões ilegível: $arquivo" >&2; return 2; }
  grep -v '^\s*#' "$arquivo" | awk 'NF{print $1}'
}

# plat_extensoes_garantir <arquivo> <comando psql...>
# Cria o que faltar e CONFERE em pg_extension. Sai != 0 nomeando a extensão que não nasceu — sem isso
# a falha aparece só muito depois, como tabela ausente numa restauração (achado do L0-06-c).
plat_extensoes_garantir() {
  local arquivo=${1:?uso: plat_extensoes_garantir <arquivo> <psql...>}; shift
  [ "$#" -gt 0 ] || { echo "plat_extensoes_garantir: falta o comando psql" >&2; return 2; }
  local psql=("$@") extensoes=() ext presentes faltam=()
  mapfile -t extensoes < <(plat_extensoes_lista "$arquivo")
  [ "${#extensoes[@]}" -gt 0 ] || { echo "lista de extensões vazia: $arquivo" >&2; return 2; }
  for ext in "${extensoes[@]}"; do
    # o nome vem de arquivo do repositório, não de entrada de usuário; ainda assim só letras, dígitos
    # e sublinhado passam, porque este texto entra num comando SQL
    [[ "$ext" =~ ^[a-z0-9_]+$ ]] || { echo "nome de extensão inválido em $arquivo: $ext" >&2; return 2; }
    "${psql[@]}" -c "CREATE EXTENSION IF NOT EXISTS $ext" >/dev/null
  done
  presentes=$("${psql[@]}" -Atc "SELECT extname FROM pg_extension ORDER BY extname")
  for ext in "${extensoes[@]}"; do
    grep -qxF "$ext" <<<"$presentes" || faltam+=("$ext")
  done
  if [ "${#faltam[@]}" -gt 0 ]; then
    echo "extensão exigida ausente depois do CREATE EXTENSION: ${faltam[*]} (lista: $arquivo)" >&2
    return 1
  fi
  echo "extensões conferidas em pg_extension: ${extensoes[*]}"
}
