# Ensaio de restauração do backup (item L0-06-c)

O backup só vale se a restauração funcionar. O job `backup.restore_drill` restaura o último dump de cada
schema num banco de ensaio, conta linha por linha contra a produção, confere o sha256 de objetos do bucket
contra o manifesto e grava o resultado em `plat.backup_drill`. Falha nunca é silêncio: vira job `falhou`,
evento `backup/falha` e e-mail ao superadmin, o mesmo caminho de notificação do dump (item L0-06-a).

## O que o ensaio faz, em ordem

1. Escolhe a linha mais nova de `plat.backup` por schema (é o dump que seria usado numa restauração real).
2. Recalcula o sha256 do arquivo e compara com o registrado. Diferente: divergência, e para por aí.
3. Cria (uma vez) o banco de ensaio `plat_drill_<schema da instalação>` com as extensões `postgis`,
   `pgcrypto`, `pg_trgm` e `unaccent`; derruba o schema restaurado de um ensaio anterior; roda
   `pg_restore --no-owner --no-privileges`.
4. Lista, na produção, todas as tabelas do schema com coluna `tenant_id` e conta `COUNT(*)` dos dois lados.
5. Confere o sha256 de até 3 objetos do bucket por inquilino contra o manifesto mais novo daquele inquilino.
6. Grava a linha em `plat.backup_drill` (tabelas, linhas, divergências, diferenças posteriores, objetos
   conferidos, duração) e derruba o schema restaurado.

## A base de comparação é o instante do dump, não "agora"

Entre o dump e o ensaio a produção continua escrevendo. Por isso o ensaio separa duas coisas:

- **divergência** (reprova e notifica): tabela que não veio na cópia restaurada, ou cópia restaurada com
  MAIS linhas que a produção — o que estava no backup sumiu da produção.
- **diferença posterior** (registrada, não reprova): produção com mais linhas que a cópia. É o que uma
  escrita depois do dump produz. A linha do ensaio guarda `dump_em` ao lado do número.

Limite honesto: uma remoção legítima de linhas depois do dump aparece como divergência. É deliberado — o
ensaio prefere um alarme para conferir a um silêncio.

## Quando roda

- Periódico mensal, dia 1 às 04:30, no inquilino técnico `plataforma` (`app/backup/periodicos.py`).
- Versão curta (um inquilino) na suíte, dentro do `make check`:
  `tests/api/test_backup_restore_drill.py::test_01_drill_curto_de_demo2_sem_divergencia`.
- À mão: `POST /api/jobs` com `{"tipo": "backup.restore_drill", "parametros": {"somente": ["<slug>"]}}`.

## Onde ver o resultado

- `plat.backup_drill` pelas funções `plat.backup_drill_listar(<schema>, <limite>)` (inquilino técnico).
- `GET /saude`, bloco `backup_drill`: data do último ensaio, se passou, quantos schemas, quantas
  divergências e a duração. Só o agregado — a página de status responde sem sessão.

## O que este item mediu (07/09/2026, base de trilha)

| medida | valor |
|---|---|
| ensaio curto (um inquilino), ponta a ponta, com o banco de ensaio já criado | 3,7 s, carga 7,20 (teto da cláusula: 60 s) |
| o mesmo ensaio na rodada que teve de criar o banco de ensaio | 21,2 s, carga 10,15 |
| tabelas com `tenant_id` conferidas no inquilino | 4 |
| linhas contadas na cópia restaurada | 262 |
| objetos do bucket conferidos contra o manifesto | 1 |
| tabelas com `tenant_id` no schema da plataforma | 49 |
| 3 linhas escritas depois do dump | acusadas como diferença posterior, delta 3 |
| 1 byte trocado no dump | job `falhou`, linha `ok=false`, evento e e-mail |

Números de tempo vêm com a carga da máquina ao lado em `tests/medidas/L0-06-c-restore-drill.json`.

## Achado do primeiro ensaio de verdade: o dump do schema da plataforma exige 4 extensões

Restaurar o dump de `plat` num banco só com PostGIS perde a tabela `item` em silêncio: sem `unaccent` a
configuração de busca `pt_sem_acento` não nasce e a tabela não é criada; o ensaio acusou "tabela ausente na
cópia restaurada". O `install.sh` cria só `postgis` e `pgcrypto`; `pg_trgm` e `unaccent` entraram com o
geocodificador (migração 045), que as declara como já instaladas na casa. Consequências práticas:

- o banco de ensaio cria as quatro antes de restaurar (`drill.EXTENSOES_DO_ENSAIO`);
- **numa restauração de verdade em máquina nova, crie as quatro extensões antes do `pg_restore`**;
- fica registrado aqui que o `install.sh` cobre só duas. Fechar essa lacuna é decisão do item de instalação,
  não deste; o ensaio serve justamente para ela não passar despercebida.

## Limpeza

O banco `plat_drill_*` fica na máquina entre ensaios (é ele que evita pagar `createdb`/`dropdb` a cada
rodada: medido em 07/09, `dropdb` de um banco com PostGIS levou de 32 a 92 s com a máquina em carga 12).
Ele só guarda o schema restaurado durante o ensaio; ao fim, o schema é derrubado. Para removê-lo por
completo: `sudo -u postgres dropdb --if-exists plat_drill_<schema>`.
