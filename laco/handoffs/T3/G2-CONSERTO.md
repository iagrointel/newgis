# G2-CONSERTO — consertos dos achados do adversário do grupo G2 (catálogo L0-03)

Trilha `wt/g2fix`, worktree `/home/dev/plataforma/wt/g2fix`, base própria `plat_tg2fix`
(`bash /home/dev/plataforma/laco/trilha_ambiente.sh g2fix`). Data: 06/09/2026.
Laudo atacado: `laco/handoffs/T3/ataque-g2-ADVERSARIO.md`. Testes do adversário: ramo `wt/adv2`, commit
`9f855ad`, trazidos para este ramo por `git cherry-pick` (commit `561b78d`) e NUNCA apagados nem afrouxados.

Commits do ramo (além do cherry-pick do adversário):

| commit | o que |
|---|---|
| `3ccde57` | lixeira (G2-4), transferência (G2-5), compactação (G2-3), cache da miniatura (G2-6), estrela (G2-9) |
| `5a9f5e2` | notificação interna (G2-7); marca xfail retirada do teste de tela |
| (este) | ADR, CHANGELOG, medidas e este handoff |

## Estado dos nove achados

| achado | estado | marca do teste |
|---|---|---|
| G2-1 versões de outro inquilino apagadas pela função | **NÃO MEXI** (ressalva do gerente) | segue `xfail(strict=True)` |
| G2-2 fila aceita item de outro inquilino | **NÃO MEXI** (mesma ressalva) | segue `xfail(strict=True)` |
| G2-3 compactação deixa 146 linhas | consertado | marca retirada, teste exige ≤ 50 |
| G2-4 esvaziar lixeira apaga tudo | consertado nos dois níveis | marca retirada, teste exige recusa + efeito |
| G2-5 evento de transferência falso | consertado | marca retirada, teste exige 409 e ausência de evento |
| G2-6 miniatura por link cacheável | consertado | marca retirada |
| G2-7 notificação interna inexistente | construída, item ainda PARCIAL | marca retirada |
| G2-8 funções do `plat` com EXECUTE para PUBLIC | **NÃO MEXI** (permissão de função) | segue `xfail(strict=True)` |
| G2-9 estrela de favorito com estado errado | consertado | marca retirada, e2e passa 3 de 3 |

Reproduzir tudo:

```
bash /home/dev/plataforma/laco/trilha_ambiente.sh g2fix
cd /home/dev/plataforma/wt/g2fix && ln -sfn /home/dev/plataforma/enterprise/venv venv
set -a; source /home/dev/plataforma/laco/var/trilha/g2fix.env; set +a
venv/bin/pytest tests/api/catalogo/test_adversario_g2.py -q -p no:randomly     # xx.....x
```
Aviso de ambiente: `laco/trilha_ambiente.sh` lê as migrações de `/home/dev/plataforma/enterprise/db/migracoes`,
não do worktree. A migração nova desta trilha foi aplicada à mão na base `plat_tg2fix`:
`TRILHA=g2fix laco/trilha_reescrever.py db/migracoes/20260906T1607_notificacao_interna.sql | sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f -`
seguido do INSERT em `plat_tg2fix.versao_migracao`. Quem repetir a partir do zero precisa do mesmo passo enquanto
o ramo não voltar a `master`.

## 1. Perda de dado (G2-4) — `POST /api/lixeira/esvaziar`

**Achado.** O pedido com identificador que a segurança de linha não resolve enfileirava `{"dias": 0, "ids": []}`;
a tarefa fazia `[str(x) for x in ids] if ids else None`, `[]` virava `NULL` e `plat.lixeira_expurgar(0, now(),
NULL)` devolvia TODA a lixeira do inquilino. Medido pelo adversário: pedido de 1 item inexistente → 2 candidatos
ao expurgo, que é físico (`destruidores.destruir` + `plat.item_expurgar`).

**Conserto (dois níveis).**
- `app/catalogo/rotas_lixeira.py::esvaziar`: guarda `pediu_ids`; se o pedido nomeou identificadores e nenhum
  resolveu, 404 `nenhum_item_na_lixeira`; se não há nada para expurgar, 409 `lixeira_vazia`. Nenhum job é criado.
- `app/catalogo/tarefas.py::catalogo_lixeira_expurgar`: `None` (varredura por idade, o periódico) deixou de ser a
  mesma coisa que `[]` (lista que não resolveu). Lista vazia levanta `FalhaDefinitiva`; e, se o banco devolver
  mais candidatos do que a lista pediu, a tarefa também recusa antes de destruir qualquer coisa.
- Mesma correção em `catalogo.exportar_lista`, onde `[]` exportava tudo (sem perda, mas o mesmo erro).

**Prova.** `tests/api/catalogo/test_adversario_g2.py::test_g2_4_...` (sem xfail) exige três coisas: a rota
responde 404 com o código certo; a tarefa levanta com `ids=[]`; e um pedido legítimo de UM item alcança
exatamente 1 candidato enquanto a lixeira tem 2, e `plat.lixeira_expurgar(0, now(), ARRAY[]::uuid[])` alcança 0.
`tests/api/cruzado_casos.py` deixou de admitir 202 nessa rota: A pedindo o item de B agora recebe 404.

## 2. A auditoria mente (G2-5) — transferência de dono

**Achado.** `UPDATE ... WHERE id = ...` barrado pela segurança de linha afeta zero linhas e NÃO levanta erro. A
transferência gravava `itens/transferir` de um item arrastado que não mudou de dono: a API respondia 200, o
histórico dizia "de 9 para 2" e o dono continuava sendo o 9.

**Conserto.** `app/catalogo/transferencia.py`:
- `_arrastados` passou a trazer `plat.pode_editar(i.id)`, e `planejar` declara a falha `arrasto_sem_edicao` (com
  rótulo em `web/js/i18n/pt-BR.json`) para o item dependente que o ator não pode editar. A pré-checagem avisa
  ANTES em vez de prometer o arrasto.
- Em `executar`, todo `UPDATE` de dono confere `cur.rowcount != 1` e levanta 409 `transferencia_sem_efeito`. A
  transação inteira cai: ninguém fica com meia transferência gravada, e o evento só existe depois da linha mudar.

**Prova.** `test_g2_5_...` (sem xfail) monta a mesma cena do adversário e exige: a simulação traz
`arrasto_sem_edicao` e `com_falha == 1`; executar responde 409 `plano_com_falhas`; o dono da vista continua o
mesmo; e NÃO existe evento `itens/transferir` para a vista nem para a camada.

**Efeito colateral honesto.** Quem transfere uma camada cuja vista é de outro dono agora é bloqueado, em vez de
receber 200 com um arrasto que não aconteceu. Admin com `conteudo.editar_tudo` (que é quem `pode_editar`
enxerga) continua transferindo os dois.

## 3. Metade de um item não existe (G2-7) — notificação interna

**Achado.** Nenhuma rota, tabela, migração ou linha de código de notificação (`grep` por "notific" = 0), mas o
portão do L0-03-k pede sino, lida/não lida, dedup por chave, expurgo de 90 dias e "sino consulta ≤ 20 ms".

**Construído.** Migração `db/migracoes/20260906T1607_notificacao_interna.sql`:
`plat.notificacao` (índice único `(usuario_id, chave)` = dedup; índice parcial `(usuario_id) WHERE lida_em IS
NULL` = sino), segurança de linha por `usuario_id` para ler/marcar/apagar mais uma política só de INSERT que
deixa notificar OUTRO usuário do inquilino sem poder lê-lo; `plat.notificar` (SECURITY DEFINER com REVOKE de
PUBLIC e GRANT para `plat_app` e `plat_worker`, teto por minuto, dedup) e `plat.notificacoes_expurgar`.
Código: `app/notificacoes.py`, `app/rotas_notificacoes.py` (`GET /api/notificacoes/contagem`, `GET
/api/notificacoes`, `POST /api/notificacoes/lidas`, `DELETE /api/notificacoes/{id}`), emissão em
`app/auth/rotas_grupos.py` (convite e pedido de entrada) e `app/jobs/worker.py::_notificar_dono` (fim de job),
periódico `catalogo.notificacoes_expurgar` às 04:20, sino em `web/js/base/notificacoes.js` + `layout.js` +
`style.css` + `pt-BR.json`.

**Prova.** `tests/api/catalogo/test_notificacoes.py`, 7 testes, todos verdes:
convite notifica o convidado e o sino conta (e quem convidou não recebe nada); notificação de outro usuário é
invisível na lista, 404 no DELETE e 404 no marcar-lida; chave repetida não duplica (a segunda chamada devolve
NULL e a tabela tem 1 linha); 500 pedidos seguidos criam no máximo 60 (teto por minuto); marcar uma e marcar
todas zeram o sino, e `{"ids": [], "todas": false}` é 422 (lista vazia nunca é "todas"); expurgo por idade apaga
a de 200 dias e deixa a de 1 dia. Medida gravada em `tests/medidas/L0-03-catalogo.json`:
**`sino_consulta_p95_ms` = 0,384 ms** (teto do portão: 20 ms) e `sino_http_p95_ms` = 19,93 ms.

**⛔ O ITEM L0-03-k CONTINUA PARCIAL.** A hipótese lista cinco origens; **"item compartilhado comigo" e "prazo de
token" NÃO emitem notificação** nesta passagem. A primeira precisa de decisão de leque (compartilhar com um grupo
de 500 pessoas geraria 500 linhas: limite de destinatários ou uma notificação por grupo); a segunda depende do
relógio de expiração de token do L0-02-d. Cláusula do portão que fica pendente, literal: *"receber notificação de
convite e de job concluído"* está feito; *"item compartilhado comigo"* e *"prazo de token"*, da hipótese, não.
Também não há captura de tela do sino (o e2e com playwright desta trilha só rodou o caso do favorito).

## 4. Portão numérico (G2-3) — compactação de versões

**Achado.** Uma passada deixa `manter + teto((N - manter)/10)` linhas: 146 depois de mil gravações, contra o teto
de 50 da refutação. O periódico rodava uma vez por dia.

**Conserto (sem tocar na função do banco).** `app/catalogo/tarefas.py::compactar_item` repete a passada até
estabilizar; o ponto fixo é `manter + 1` linha, então o chamador pede `manter = teto - 1`. O periódico passou de
`40 3 * * *` para `40 * * * *`.

**Prova medida (nesta trilha).** 1.000 PUTs no mesmo item em 21,4 s → 1.001 linhas de versão. `compactar_item(cur,
item, 50)` removeu 951 e deixou **50 linhas em 40 ms**; a passagem seguinte removeu 0. Gravado em
`tests/medidas/L0-03-catalogo.json` como `versoes_linhas_apos_compactacao`. O teste do adversário
(`test_g2_3_...`, sem xfail) faz o mesmo com 200 PUTs e exige ≤ 50 linhas e estabilização.

**O número NÃO foi renegociado**: continua 50. O que o ADR registra é que 50 linhas = 49 versões íntegras + 1
linha `compactada` que resume tudo o que veio antes.

## 5. Menores (G2-6 e G2-9)

**G2-6.** `app/catalogo/miniatura.py::entregar` recebe o `Cache-Control` de quem chama (`CACHE_SESSAO` =
`private, max-age=300`; `CACHE_SEM` = `no-store, must-revalidate`) e as duas rotas anônimas de
`rotas_compartilhamento.py` (link por token e pública) passam `CACHE_SEM`. Prova: `test_g2_6_...` sem xfail.

**G2-9.** `web/js/catalogo/contexto.js` ganhou `marcaFavoritos` / `marcarFavoritoLocal` /
`aplicarFavoritosLocais`: cada mudança de favorito recebe um número de ordem, `lista.carregar` guarda a marca de
ANTES do pedido e reaplica as mudanças posteriores sobre a resposta que chegar atrasada. Em `lista.js` a intenção
é registrada antes da chamada (e desfeita em erro), então a corrida some mesmo se a resposta chegar entre o
clique e o 204. Prova: `tests/e2e/test_adversario_g2_conteudo.py` (marca retirada) passou **3 de 3** contra
`https://127.0.0.1:8157` (harness `tests/e2e/adv2_servidor.py`, certificado autoassinado, servidor derrubado pelo
identificador de processo ao fim); `tests/e2e/test_conteudo.py` roda até o fim no mesmo servidor.

## 6. Cláusula impossível (portão do L0-03-f)

A refutação pede "nome de item de 2.048 caracteres"; `plat.item` tem `CHECK (length(titulo) BETWEEN 1 AND 250)` e
`limites.ITEM_TITULO_MAX = 250`. **Decisão: fica o banco, muda a cláusula** — 250 é o teto do produto de
referência, já está publicado em `docs/LIMITES.md` e no OpenAPI, e título de 2 mil caracteres é descrição, não
nome (o item já tem `resumo` até 5.000 e `descricao_html`). Registrado em
`docs/adr/20260906T1623-consertos-do-ataque-g2.md` seção 2. Prova do que dá para exercer:
`test_titulo_no_teto_de_250_e_recusa_acima` — 250 passa em criar e renomear, 251 é 422 nos dois.
**Pendência para o gerente:** corrigir a linha da refutação do `L0-03-f-tela-conteudo` em `laco/estado.json`
(esta trilha não edita o estado).

## Ressalva respeitada

Não foi tocado `plat.item_versoes_compactar`, nenhuma permissão de função e nenhuma outra função SECURITY
DEFINER existente. A única função definidora NOVA é `plat.notificar` (mais `plat.notificacoes_expurgar`), criada
já com `REVOKE ALL ... FROM PUBLIC` e GRANT nominal — a trilha das 102 funções vai encontrá-la em conformidade.
Os testes `test_g2_1`, `test_g2_2` e `test_g2_8` continuam `xfail(strict=True)` de propósito: quando aquela
trilha consertar, viram XPASS e alguém tira a marca.

## Suíte e limitações honestas

`venv/bin/pytest tests/api/catalogo tests/unit -p no:randomly` na base `plat_tg2fix`:
**2.162 passaram, 3 falharam, 3 xfailed, 2 erros** em 62,8 s. As 3 falhas e os 2 erros já existiam antes desta
trilha e nenhum é do que foi consertado aqui:
- `test_eventos_e_seguranca::test_funcoes_do_catalogo_sem_public...` = o achado G2-8, da outra trilha;
- `test_documento::test_integridade_acusa_linha_de_versao_editada...` = item L5-05, fora deste grupo (o próprio
  adversário registrou que ele se sustenta sozinho no master);
- `test_migracoes_nome_e_dependencia::test_a_familia_legada_esta_fechada...` = `049_convite_resolver_config.sql`,
  migração de OUTRA trilha com número de três dígitos depois do 048 (não é minha; o gerente decide se renomeia);
- os 2 erros (`test_lixeira::test_expurgo_com_relogio_simulado`, `test_miniatura::test_job_de_camada_semeada`)
  exigem `plat-worker` vivo, que o brief proíbe subir.

Lint: `ruff check app tests` = 11 erros, todos pré-existentes no master (o master tinha 12; um foi corrigido em
`tests/e2e/adv2_servidor.py`, só ordenação de import). `make sem-marcador` continua acusando dois arquivos de
outras trilhas (`app/geocodificador/motor.py`, `app/settings.py`); nenhum arquivo desta trilha aparece.
`docs/LIMITES.md` regenerado; `docs/openapi.json` regenerado com as quatro rotas novas, e cada uma delas ganhou
entrada em `tests/api/cruzado_casos.py` e em `tests/api/eventos_esperados.py`.

**Não medido:** a notificação de fim de job pelo worker foi lida no código e a função que ela chama está provada
em teste, mas nenhum worker vivo rodou nesta trilha — o elo do meio não é medição minha. Também não medi de novo
`busca_p95_ms`, `pagina_conteudo_ms` nem as capturas do portão do L0-03-f.

## Riscos de junção (arquivos que a árvore principal também mexe)

`app/main.py` (duas linhas: import e uma entrada em ROUTERS), `app/limites.py` (três constantes no fim do bloco
do catálogo), `app/catalogo/tarefas.py` e `app/catalogo/periodicos.py` (blocos novos, sem tocar nos existentes),
`app/jobs/worker.py` (um `elif` em `_terminar` e um método novo), `docs/openapi.json` e `docs/LIMITES.md`
(gerados: em conflito, regerar em vez de resolver à mão), `CHANGELOG.md` (entrada nova no topo do turno 3).
