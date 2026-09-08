# FASE 0 — fim da colisão de numeração de migração (carimbo de tempo, ADR 0014)

Árvore: `/home/dev/plataforma/enterprise`, ramo `master`. Commit único: **13b419f**.

## O problema, medido
`plat.versao_migracao` é chaveada pelo NOME do arquivo. Renumerar um arquivo já aplicado faz `db/migrar.sh`
tratá-lo como novo e aplicá-lo de novo, e deixa o nome antigo órfão na tabela. Em 06/09 o mesmo arquivo foi
renumerado três vezes (031 → 037 → 044 → 045). O estrago está em disco hoje: `plat` tem **45 linhas** em
`versao_migracao` contra **41 arquivos** em `db/migracoes`, e as 4 órfãs são exatamente
`031_raster_item`, `042_garage_inquilino`, `044_amc`, `044_uploads` — nomes que já não existem.
`tests/api/test_saude.py` fechava o cerco pelo outro lado: casava `[0-9][0-9][0-9]_*.sql` e exigia que a
última do glob fosse a `ultima_migracao` do `/saude`.

## O que foi construído
| arquivo | o que é |
|---|---|
| `app/migracoes.py` (novo) | módulo puro: `RE_MIGRACAO_LEGADO`, `RE_MIGRACAO_CARIMBO`, `ULTIMO_LEGADO=48`, `chave_migracao`, `listar`, `dependencias`. Não importa settings nem abre banco. |
| `app/db.py` | `migracoes_em_disco` usa `app.migracoes.listar`; `migracoes_estado` ordena em Python pela chave, não com `ORDER BY nome`. |
| `db/migrar.sh`, `db/migrar_homolog.sh` | função `listar_migracoes` em bash com a MESMA chave. |
| `/home/dev/plataforma/laco/trilha_ambiente.sh` | mesma função (não é do repositório, não entra no commit). |
| `tests/unit/test_migracoes_nome_e_dependencia.py` (novo) | 5 portões + a prova do próprio portão de dependência. |
| `tests/api/test_saude.py`, `test_migracoes.py` | usam `migracoes_em_disco`; o novo significado de "última" está escrito no teste. |
| `docs/adr/0014-nome-de-migracao-por-carimbo-de-tempo.md` (novo) | a decisão, seções 1 a 6. |
| `/home/dev/plataforma/laco/BRIEF_WORKTREES.md` | regra 5 reescrita + seção "Nome de migração"; o adendo de reserva de número (garage=034, stac=035, valida=036, amc=037) foi REMOVIDO por obsoleto. |
| `CHANGELOG.md` | entrada no turno 3. |

## A regra
- Migração nova: `db/migracoes/YYYYMMDDTHHMM_<slug>.sql`, `date -u +%Y%m%dT%H%M`. Mesmo minuto em outra
  trilha: 3 hexadecimais logo após o minuto (`20260906T1537a01_...`).
- Legado de três dígitos FECHADO e imutável. O corte é **048**, não 047, porque
  `048_smtp_convites_correcoes.sql` já estava em disco (trilha paralela, ainda sem commit) quando a regra
  entrou — e a primeira regra do ADR é que arquivo existente não é renomeado.
- Ordem: chave `("0", nome)` para o legado, `("1", nome)` para o carimbo. Todo o legado antes de qualquer carimbo.
- Dependência do mesmo minuto: `-- depende: <arquivo>.sql` no cabeçalho. O teste reprova se o alvo não
  existir ou vier depois na ordem. Conserta-se renomeando a SUA, nunca a outra.

## Prova (cláusula 6 da tarefa)
Duas migrações no mesmo minuto UTC, uma dependendo da outra:
`20260906T1537a01_prova_carimbo_trilha_a.sql` e `20260906T1537b02_prova_carimbo_trilha_b.sql`
(esta com `-- depende:` na primeira). Aplicadas em duas trilhas independentes:

    bash /home/dev/plataforma/laco/trilha_ambiente.sh mig1   # incremental,  6,7 s
    bash /home/dev/plataforma/laco/trilha_ambiente.sh mig2   # do zero,     93,5 s

Resultado: as duas aplicaram nas duas trilhas, na ordem declarada, 43 linhas em `versao_migracao` de cada
schema contra 43 arquivos em disco, sem colisão e sem reaplicação.

    mig1 | a | 15:37:41.546   mig2 | a | 15:39:17.231
    mig1 | b | 15:37:43.016   mig2 | b | 15:39:19.845

Limpeza feita: os dois arquivos foram apagados e os dois schemas (`plat_tmig1`, `plat_tmig2`, mais os
`plat_trabalho_t*`) removidos com CASCADE, junto dos `.env`/`.segredos`/credenciais.
⚠ **Enquanto os dois arquivos de prova estiveram em disco (~5 min), OUTRAS trilhas os aplicaram sozinhas**:
`plat`, `plat_tdestrava`, `plat_tl602c`, `plat_tl208a`, `plat_tl09a`. Todas foram limpas (tabela
`prova_carimbo` derrubada e as linhas removidas de `versao_migracao`); conferido: 41 = 41 em cada uma,
`plat` de volta às suas 45 linhas de antes. Isto é um achado próprio: **arquivo posto em `db/migracoes`
é aplicado por qualquer trilha que rode nos minutos seguintes** — nunca deixar arquivo de teste lá.

## Suíte (cláusula 7)
    set -a; source /home/dev/plataforma/laco/var/trilha/mig1.env; set +a
    venv/bin/pytest tests/api/test_saude.py tests/api/test_migracoes.py tests/unit -q

1 reprovação, **alheia a esta tarefa**: `test_saude_200_com_json_do_contrato` para em
`j["fila"]["workers_vivos"] >= 1` (linha 35), DEPOIS de todas as afirmações de migração terem passado.
Causa medida: nenhum trabalhador roda contra schema de trilha — `select count(*) from plat_tmig1.worker`
= 0, `plat_tadv1.worker` = 0, `plat.worker` = 1. É limitação do ambiente isolado, não do código.
`tests/unit` inteiro passou, incluindo os 46 casos do arquivo novo.

## O que ficou de fora, e por quê
1. **As 4 linhas órfãs em `plat.versao_migracao`** (031_raster_item, 042_garage_inquilino, 044_amc,
   044_uploads) NÃO foram removidas: é dado de produção, e apagá-las é decisão do gerente, não minha.
   Enquanto estiverem lá, `test_tabela_reflete_os_arquivos_em_disco` reprova contra `plat`. Comando, se
   autorizado (o SQL das quatro já foi reaplicado sob o nome novo, então nada se perde):
   `DELETE FROM plat.versao_migracao WHERE nome IN ('031_raster_item','042_garage_inquilino','044_amc','044_uploads');`
2. `048_smtp_convites_correcoes.sql` não foi tocada nem commitada — é de outra trilha.
3. `app/db.py` tinha também uma mudança de POOL (`PLAT_POOL_MIN/MAX`) de outro agente. Ela ficou FORA do
   commit: o `git apply --cached` levou só os dois trechos de migração. Ela continua em disco, sem commit.
4. `README.md`, `ARQUITETURA.md` e `docs/adr/0001-fundacao.md` ainda dizem `NNN_*.sql`. Não foram
   alterados para não colidir com as trilhas que mexem neles; o ADR 0014 declara que substitui a seção 5
   do 0001.

## Para o adversário reproduzir
    cd /home/dev/plataforma/enterprise && git show 13b419f --stat
    venv/bin/pytest tests/unit/test_migracoes_nome_e_dependencia.py -q        # 46 casos
    venv/bin/python -c "from app.migracoes import listar; from pathlib import Path; print(listar(Path('db/migracoes'))[-3:])"
    bash -c 'source db/migrar.sh 2>/dev/null; true'   # a função listar_migracoes está no topo do script
    # refazer a prova: criar dois YYYYMMDDTHHMM<hex>_x.sql, rodar trilha_ambiente.sh em duas trilhas,
    # APAGAR os arquivos em seguida (ver o aviso acima) e limpar todo schema que os tiver pego.
