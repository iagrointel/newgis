# ADR 20260907T2230 — ensaio de restauração do backup (item L0-06-c)

## Contexto

O item L0-06-a passou a produzir dumps lógicos por inquilino com sha256 em `plat.backup`. Dump registrado
não é backup provado: o que decide numa perda é a restauração. Faltava um ensaio periódico que restaure o
último dump e compare o resultado com a produção.

## Decisão

1. **Job `backup.restore_drill`**, no inquilino técnico, periódico mensal (dia 1, 04:30), com versão curta
   (um inquilino) dentro da suíte, logo dentro do `make check`.
2. **Banco de ensaio reusado, schema descartado a cada rodada.** A primeira versão criava e derrubava um
   banco por ensaio; `dropdb` de um banco com PostGIS custou de 32 a 92 s nesta máquina em carga 12, e o
   ensaio curto passava de 60 s por causa disso. O banco `plat_drill_<schema>` passa a ser criado uma vez
   (com `postgis`, `pgcrypto`, `pg_trgm`, `unaccent`) e cada ensaio cria e derruba DENTRO dele o schema
   restaurado. O ensaio curto caiu para 21,2 s na rodada que cria o banco (carga 10,15) e 3,7 s nas seguintes
   (carga 7,20).
3. **A comparação é contra o instante do dump.** Cópia restaurada com mais linhas que a produção, ou tabela
   que não veio, é divergência (reprova e notifica). Produção com mais linhas é diferença posterior:
   registrada com tabela e delta, não reprova. A alternativa — comparar com "agora" e chamar tudo de
   divergência — daria alarme em toda instalação viva.
4. **Notificação pelo caminho que já existe** (`_notificar_falha` do L0-06-a): job `falhou`, evento
   `backup/falha` e e-mail ao superadmin. Nada de canal novo.
5. **Publicação em `/saude`**, bloco `backup_drill`, por uma função SECURITY DEFINER que devolve só o
   agregado (data, se passou, schemas, divergências, duração). A página de status responde sem sessão, então
   não pode expor nome de arquivo nem de inquilino.

## Consequências

- Um banco `plat_drill_*` fica na máquina entre ensaios (vazio entre rodadas). O runbook diz como removê-lo.
- Uma remoção legítima de linhas na produção depois do dump aparece como divergência. Aceito: alarme para
  conferir é melhor que silêncio, e a linha do ensaio traz `dump_em` para quem confere.
- O ensaio expôs que o dump do schema da plataforma só restaura numa base com as quatro extensões, e que o
  `install.sh` cria duas. Registrado em `docs/RUNBOOKS/restauracao.md`.
