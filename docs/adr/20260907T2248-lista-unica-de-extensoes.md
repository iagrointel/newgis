# Lista única das extensões do Postgres (item L7-01-d)

Estado: aceito · setembro de 2026

## Contexto

O schema da plataforma exige quatro extensões: `postgis`, `pgcrypto`, `pg_trgm` e `unaccent`. O
instalador criava só as duas primeiras. As outras duas entraram com o geocodificador (migração
`045_geocodificador.sql`), que se limitava a declará-las "já instaladas na casa" — verdade nesta
máquina, falso em qualquer instalação nova.

A falha não aparece na instalação. Aparece muito depois: sem `unaccent`, a configuração de busca
`pt_sem_acento` não nasce, a tabela `item` não é criada e o ensaio de restauração do L0-06-c acusa
"tabela ausente na cópia restaurada". Foi assim que o defeito foi achado, no primeiro ensaio de
verdade em 07/09/2026.

Antes deste item a mesma lista existia escrita à mão em dois lugares (o `install.sh` e o
`app/backup/drill.py`) e faltava num terceiro (`laco/trilha_ambiente.sh`). Uma extensão nova entrava
em um deles e não nos outros — é o mesmo tipo de defeito que este item corrige, não uma variante.

## Decisão

1. A lista mora em `db/extensoes.txt`, um nome por linha, `#` começa comentário. Mesmo formato de
   `deploy/pacotes_apt.txt`, que o `install.sh` já lê com o par `grep -v '^\s*#'` + `awk 'NF{print $1}'`.
2. `db/extensoes.sh` traz duas funções para quem lê em bash: `plat_extensoes_lista` (só lê) e
   `plat_extensoes_garantir` (cria o que falta e **confere em `pg_extension`**, saindo diferente de zero
   com o nome da extensão que não nasceu). O arquivo é feito para ser carregado com `source`, nunca
   executado, e não escreve nada fora do banco — é por isso que o teste do item consegue exercitar a
   seção "b" do instalador contra uma base descartável sem rodar o `install.sh`, que grava em `/etc/plat`
   e mexe em unidade de produção.
3. Os três consumidores leem esse arquivo: `install.sh` (seção "b"), `laco/trilha_ambiente.sh`
   (seção "0") e o ensaio de restauração, em Python, por `app.backup.drill.extensoes_do_ensaio()`.

A conferência em `pg_extension` é a parte que vale: `CREATE EXTENSION IF NOT EXISTS` sozinho já era o
que o instalador fazia, e um `CREATE` que não acontece só é notado dias depois, numa restauração.

## Consequências

- Extensão nova é uma linha em `db/extensoes.txt`, e os três caminhos passam a exigi-la no mesmo commit.
- `laco/trilha_ambiente.sh` vive fora do repositório e serve trilhas de vários ramos ao mesmo tempo.
  Enquanto este ramo não estiver em master, worktree antigo não tem os dois arquivos: nesse caso a
  seção "0" avisa e segue, que era o comportamento anterior. O aviso some quando o ramo entra.
- O `pg_restore` de um schema desta casa continua saindo com código diferente de zero por causa de
  vistas e chaves estrangeiras que apontam para o schema `acervo` (ativo da casa, fora da plataforma).
  A prova de restauração continua sendo a presença dos objetos, como já era em
  `app/backup/tarefas.py::_restaurar_e_contar`, e o teste do item confere que nenhum erro fora do
  `acervo` aparece.

## Limite honesto

O portão fala em "install.sh numa base só com PostGIS". O que foi medido é a função de extensões do
`install.sh` contra uma base recém-criada só com PostGIS, seguida da restauração do dump nessa base.
O `install.sh` inteiro não é rodado por nenhum teste: ele instala pacotes, escreve unidades do systemd
e pede certificado, e rodá-lo nesta máquina mexeria na instalação de produção.
