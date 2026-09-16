# Laudo — tests/api/conexao (26 falhas pré-existentes)

Ramo `wt/f2fixconexoes2`, a partir de `wt/uniao`. Trilha de teste `uniao` (schema `plat_tuniao`).

## Item 1 — google_sheets: CHECK + roteamento (PASSA, isolado da fila)
`db/migracoes/20260916T1530_conexao_tipo_check_conserto_fusao.sql` reconstrói
`plat.conexao_tipo_check` com a lista completa e deduplicada de `app/limites.py CONEXAO_TIPOS`
(três migrações anteriores — 06/09 google_sheets, 07/09 xyz, 08/09 odk_ponte — sobrescreveram
essa CHECK cada uma com a lista que enxergava, e a última apagou 'xyz' e 'google_sheets').
Aplicada à trilha `uniao` via `laco/migrar_trilha.sh uniao <worktree>`.

`app/conexao/rotas.py` nunca chamava `google_sheets.url_exportacao_csv`/`validar_conta_servico`/
`cabecalhos_auth` — restaurado em `criar`/`editar`/`testar`. `google_sheets.py` chamava
`seguranca.buscar_seguro(conteudo=...)`, parâmetro que virou `corpo_envio` num item posterior —
corrigido. `arquivo_url.baixar()` perdeu o parâmetro `cabecalhos` (só tinha `credencial`, vira
Bearer direto — errado para google_sheets, cuja credencial é o JSON da conta de serviço, não um
token) — devolvido, e `tarefas_arquivo.py`/rota `PUT /{id}/arquivo` reganharam o mesmo tratamento.

Prova: `test_url_de_planilha_e_normalizada_na_criacao` e `test_credencial_invalida_recusada_na_entrada`
(não usam fila) passam sempre, isolados ou não. Os outros 5 testes do arquivo dependem de um job
`conexoes.arquivo_sincronizar` — ver item 4.

## Item 2 — pmtiles/xyz: mensagem nomeada + roteamento completo (PASSA — 9/9 estável)
`app/conexao/ladrilhos.py` (validação de config, checagem de Range/206, TileJSON) nunca era
importado por `rotas.py` — a fusão que trouxe L6-02-h/L6-02-conectores-vivos reescreveu a mesma
região do arquivo e derrubou a chamada. Restaurado: `_config_tiles_ok`/`_range_pmtiles_ok` em
`criar`/`editar`, rota `GET /{id}/tilejson`. `tests/api/conexao/test_pmtiles_xyz_tilejson.py`:
`URL_PMTILES_PUBLICA` (demo-bucket.protomaps.com, medida 07/09) saiu do ar (HTTP 404 confirmado por
curl em 16/09) — trocada pelo dataset de amostra oficial da Protomaps em `r2-public.protomaps.com`
(206/accept-ranges confirmado). Removida 1 conexão órfã (`zt-tiles-pmtiles-sem-range`) gravada por
uma execução manual minha antes deste conserto.

Comando: `bash laco/roda_teste.sh tests/api/conexao/test_pmtiles_xyz_tilejson.py -q` → **9 passed**,
repetido 3× sem falha (não usa a fila de jobs — todas as rotas exercitadas são síncronas).

## Item 3 — WFS/OGC API: rotas do modo referenciado restauradas (PASSA — 8/12 sempre; 4/12 ver item 4)
`GET /{id}/colecoes`, `.../colecoes/{c}/campos` e `.../colecoes/{c}/feicoes` (mais `_conector`/
`_erro_do_conector`) tinham o mesmo destino do item 2: `app/conexao/vetor_externo.py` intacto,
nunca importado em `rotas.py`. `app/conexao/modelos.py` perdeu junto `ColecaoSaida`/`ColecoesPagina`/
`CampoSaida`/`CamposSaida`/`FeicoesSaida` — devolvidos. `cache_conexao.esquecer(...)` também
devolvido a `editar`/`apagar` (servir coleção da URL antiga depois de editar seria mentira, não cache).

A válvula `PLAT_TESTE_CONEXAO_ALVOS` (a "SSRF de teste" citada no brief) já estava correta e
intacta em `app/conexao/seguranca.py` — o problema nunca foi a válvula, foi a rota 404 por trás dela.

Comando: `bash laco/roda_teste.sh tests/api/conexao/test_wfs_ogcapi.py -q` → 8 dos 12 testes (os que
não dependem de job de cópia) passam sempre. Os 4 de cópia (`test_copia_50_mil_feicoes_com_tempo_medido`,
`test_copia_ogc_api_preserva_tipos_de_queryables`, `test_copia_wfs_so_com_gml`,
`test_wfs_de_5_milhoes_sem_paginacao_para_no_limite_e_avisa`) — ver item 4/5.

## Item extra (achado, não pedido) — `copia.py` corrompia a conexão do pool
`conexao_copiar_vetor` chamava `esquema_dado.esquema(cur, slug)` DEPOIS do `with ctx.db() as cur:`
fechar (bug do isolamento de schema de dado, 11/09 — não da fusão). A conexão já tinha voltado ao
pool; a consulta seguinte nesse `cur` reabria uma transação numa conexão que o pool achava livre, e
o PRÓXIMO checkout (`ctx.progresso`, no mesmo job) explodia em `_preparar` (`app/db.py:74`) com
`ProgrammingError: set_session cannot be used inside a transaction` — **100% determinístico antes do
conserto** (4/4 jobs de cópia falhavam sempre, sempre no mesmo traceback). Corrigido: a chamada
entrou para dentro do `with`. Traceback completo recuperado de `plat_tuniao.job_log` confirma o ponto
exato antes e depois do conserto.

## Achado que fica CAI — corrida com o worker ambiente `plat-uniao-worker.service`
Depois do conserto acima, os 4 testes de cópia (e a maioria dos testes de google_sheets que chamam
`f.sincronizar()`) continuam falhando de forma intermitente — **não pelo mesmo bug**: o traceback é
idêntico ao bug JÁ CONSERTADO aqui (`set_session cannot be used inside a transaction` em
`esquema_dado.esquema`) ou vira `erro_de_conexao:ConnectError` na sincronização do google_sheets.

Causa confirmada: `plat-uniao-worker.service` (systemd, sempre ativo) roda
`/home/dev/plataforma/wt/ux11merge/venv/bin/python -m app.jobs.worker` — OUTRO worktree, com o MESMO
bug do `copia.py` ainda presente (`git show` confirmado, linha 160 fora do `with`) e SEM o `env` de
teste (sem `SSL_CERT_FILE` da CA do servidor de teste, sem `PLAT_TESTE_CONEXAO_ALVOS`). A fila de
jobs (`plat_tuniao.job`) é compartilhada por QUALQUER worker que fizer `job_pegar` primeiro
(`SKIP LOCKED`, sem afinidade de worker) — quando o worker ambiente ganha a corrida do teste,
executa com código velho e falha; quando o worker dedicado do teste (`WorkerExtra`) ganha, passa.
Confirmado por `SELECT * FROM plat_tuniao.worker` (mostra `trilha-uniao:<pid>` com `git_sha` do
HEAD de `wt/ux11merge`, atualizando em tempo real enquanto outro agente trabalha lá) e por
`ps aux` (o processo do systemd roda literalmente do diretório `wt/ux11merge`).

**Isto está fora do escopo dos 3 itens e fora do meu worktree** (regra da casa: nunca editar
`wt/ux11merge` nem reiniciar serviço de outro ambiente). Não é flutuação de carga — é um worker
de outro ramo, com bug já identificado e sem o ambiente de teste, competindo pela mesma fila.
Reprodução: `bash laco/roda_teste.sh tests/api/conexao/test_wfs_ogcapi.py -q` repetidas vezes —
a taxa de falha dos 4 testes de cópia varia de 0/4 a 4/4 conforme quem ganha a corrida.
Recomendação: religar `plat-uniao-worker.service` depois que este conserto (ou o de `wt/ux11merge`)
chegar a produção/à trilha canônica, ou dar afinidade de worker a `plat.job_pegar` (D novo).
