# L6-01-b-view-so-leitura — handoff

Ramo `wt/t601b` · worktree `/home/dev/plataforma/wt/t601b` (worktree PRÓPRIO: `/home/dev/plataforma/wt/stac`
estava sendo escrito ao vivo por outra sessão — `app/stac/`, `app/migracao/`, `app/catalogo/procedencia.py`
apareceram entre dois `git status` meus; trabalhar lá arriscava o trabalho alheio).
Base de teste própria: schema `plat_tt601b` (`bash laco/trilha_ambiente.sh t601b`), sem `flock`, sem tocar
`plat` de produção.

## O que foi construído

| arquivo | o que é |
|---|---|
| `db/migracoes/20260906T15521aa_acervo_publicacao.sql` | schema `plat_acervo`, papel `plat_acervo_publicador` (NOLOGIN), `plat.acervo_assinatura` (RLS), `plat.acervo_pode_ler(text)`, `plat.acervo_publicacao`, 2 tipos de evento |
| `scripts/acervo_publicar.py` | publicador: cria/derruba uma view por camada `exposta`, roda como `postgres`, idempotente |
| `app/acervo/publicacao.py` | 4 rotas novas (lista, assinatura, feições GeoJSON, tile MVT) |
| `app/acervo/modelos.py` | 3 modelos pydantic novos (append no fim) |
| `app/main.py` | 2 linhas: import + `include_router` ANTES de `rotas_acervo` (senão `/api/acervo/camadas` casa com `/api/acervo/{fonte_id}`) |
| `app/schema_ambiente.py` | 4 linhas: regra de reescrita de `plat_acervo`/`plat_acervo_publicador` por ambiente |
| `tests/api/test_acervo_publicacao.py` | 17 testes, todos passando |
| `tests/api/eventos_esperados.py` | 3 linhas: evento declarado das 2 rotas de escrita (guarda `test_eventos`) |
| `tests/api/cruzado_casos.py` | caso A→B das 5 rotas novas + `camada_acervo` na `Preparacao` (guarda `test_cruzado`) |
| `tests/medidas/L6-01-b-view-so-leitura.json` | 7 medidas |
| `docs/adr/0018-publicacao-sem-copia-do-acervo.md` | decisão + as duas refutações medidas |
| `MANUAL.md` 18.3/18.4 · `ARQUITETURA.md` 15.1 · `CHANGELOG.md` | documentação |
| `docs/openapi.json` | SÓ os 4 caminhos novos e 5 esquemas inseridos (389 linhas, 0 removida) — regenerar o arquivo inteiro daria 4.443/2.332 porque o comitado já está atrasado em relação ao master (rotas `/api/org/smtp` faltando, `$ref` de `Convite` renomeado por outra trilha) |

## Portão de pronto, cláusula por cláusula

| cláusula | prova | resultado |
|---|---|---|
| inquilino A assina CAR e consulta de mapa sobre 7,36 mi responde em ≤ 100 ms (índice GiST da original) | `test_consulta_de_mapa_sobre_7_36_mi_em_ate_100_ms` — mediana de 5 `EXPLAIN ANALYZE` da consulta por caixa envolvente na view | **PASSOU · 1,534 ms** (cache quente; a 1ª leitura fria da tabela levou 2,68 s, registrado abaixo). O plano usa `Index Scan using idx_car_area_imovel_geom` |
| ...sobre 7,36 mi de imóveis | `COUNT(*)` exato = **8.406.837 linhas**; `reltuples` = 7.357.920 | **PASSOU com correção**: o "7,36 mi" do portão é a ESTIMATIVA do catálogo. As duas medidas estão gravadas separadas. `COUNT(DISTINCT cod_imovel)` NÃO foi medido (estourou 280 s) — logo "imóveis" não é número conferido, "linhas" é |
| inquilino B sem assinatura recebe 403/0 linhas em API | `test_api_403_sem_assinatura_e_200_com_assinatura` (403 `sem_assinatura` em feições e tile; 200 depois de assinar; cancelar fecha na hora) + `test_sem_assinatura_a_view_devolve_zero_linha` (0 linha na VIEW, como `plat_app`) | **PASSOU** |
| ...em tiles | `GET /api/acervo/camadas/<view>/tiles/{z}/{x}/{y}.mvt` 403 sem assinatura, 115.621 bytes com | **PASSOU pela API**; **PENDENTE por Martin** (ver fronteiras) |
| ...em FeatureServer | — | **PENDENTE**: FeatureServer não existe no repositório |
| nenhuma tabela public tem GRANT direto a plat_app (varre pg_class/aclexplode) | `test_nenhuma_tabela_public_tem_grant_direto_a_plat_app` — varredura de `pg_class` × `aclexplode` para `current_user`, feita como `plat_app` | **PASSOU · lista vazia** |
| e2e adiciona ao mapa | — | **PENDENTE**: `/mapa` só desenha o mapa-base PMTiles (L2-01-mapa-web não construído) |

## Refutação exigida — as três tentativas do adversário, escritas como teste negativo

1. **SELECT direto em `public.car_area_imovel` como `plat_app`** →
   `test_banco_recusa_select_direto_na_tabela_de_origem`: `psycopg2.errors.InsufficientPrivilege`,
   "permission denied for table car_area_imovel". Recusa do BANCO, com a role da aplicação, não da rota.
2. **A view sem assinatura** → `test_sem_assinatura_a_view_devolve_zero_linha` (0 linha) e
   `test_porteiro_vira_filtro_de_uma_vez_e_nao_varre_a_tabela` (o plano traz `One-Time Filter` e o nó do
   índice sai `(never executed)`: a tabela nem é lida).
3. **applyEdits na camada** → não existe FeatureServer para atacar. O que foi provado no lugar, e é mais
   fundo: `test_banco_recusa_escrita_na_view[delete|update|insert]` — `INSERT`/`UPDATE`/`DELETE` na view são
   recusados pelo Postgres para `plat_app`; `test_privilegios_da_view_sao_so_select` lê o ACL do catálogo e
   confere que o privilégio da view para `plat_app` é exatamente `{SELECT}`; e
   `test_verbo_de_escrita_na_camada_publicada_e_405` confere os 405 na superfície HTTP.

## Duas cláusulas da HIPÓTESE foram refutadas por medição (ADR 0018)

- **`SECURITY INVOKER` é impossível junto com "nenhum GRANT direto a plat_app"**. Com
  `security_invoker = true` o privilégio checado passa a ser o da tabela de ORIGEM.
  `test_security_invoker_seria_negado_pelo_banco` cria a view invoker a cada rodada e prova a recusa. A view
  ficou no modo padrão (definer), dona `plat_acervo_publicador`.
- **`security_barrier` derruba o índice GiST**. O `&&` de geometria não é `LEAKPROOF`
  (`pg_proc.proleakproof = false`); com barrier a consulta vira `Seq Scan` — cancelei a medição depois de
  **2 min 10 s**, contra 1,5 ms sem barrier. `test_security_barrier_derrubaria_o_indice_gist` compara os dois
  planos. O que protege no lugar é o porteiro ser argumento constante sem coluna: vira `One-Time Filter`.
  **Limite honesto**: se o porteiro passar a depender de coluna (assinatura por UF, por exemplo), deixa de ser
  `One-Time Filter` e a análise inteira tem de ser refeita.

## O que ficou de fora, e por quê

- **Martin** (`plat-martin`, porta 8151) não existe nesta máquina — `ARQUITETURA.md` seção 2 já dizia
  "porta reservada, serviço inexistente". O SQL de tile que ele publicaria existe e é servido pela API, com o
  porteiro dentro; "Martin serve tiles pela função com inquilino" fica pendente do serviço.
- **FeatureServer e OGC API de feição** (L2-04) não existem no repositório. `applyEdits = 405` literal
  depende deles.
- **e2e "adiciona ao mapa"** depende de L2-01-mapa-web.
- **A camada CAR não seria publicada em produção hoje.** No registro vivo, `acervo.fonte` da fonte
  `sfb-sicar-nacional-perimetros-e-camadas-do-car` está SEM licença escrita, então `acervo_sync.py` a marca
  `pendente_de_licenca` e o publicador a ignora (regra D17). O teste semeia a linha do registro como
  `postgres` — está escrito no topo do arquivo de teste. Publicar CAR de verdade depende de o item
  L6-01-g escrever a licença. Das camadas COM licença nesta base, todas as com geometria estão em schema com
  nome de cliente, que não entra em código nem em documento.
- **Dependência aberta `L0-02-tenant-auth`**: não bloqueou nada. O contexto de inquilino (`plat.tenant_id`) e
  as sessões de `demo`/`demo2` já funcionam; o porteiro usa o mesmo GUC da RLS do resto da plataforma.

## Como o adversário reproduz

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh t601b
cd /home/dev/plataforma/wt/t601b
# a migração deste item ainda não está no repositório principal que o trilha_ambiente.sh lê; aplique-a à mão:
TRILHA=t601b /home/dev/plataforma/laco/trilha_reescrever.py \
  db/migracoes/20260906T15521aa_acervo_publicacao.sql > /tmp/mig.sql && chmod 644 /tmp/mig.sql
sudo -u postgres psql -d iagro_sat -X -v ON_ERROR_STOP=1 -1 -f /tmp/mig.sql
set -a; source /home/dev/plataforma/laco/var/trilha/t601b.env; set +a
venv/bin/pytest tests/api/test_acervo_publicacao.py -q          # 17 passed
```

Provas manuais, todas como `plat_tt601b_app` (não como postgres):

```bash
sudo -u postgres psql -d iagro_sat -c "SET ROLE plat_tt601b_app; SELECT count(*) FROM public.car_area_imovel;"
#   ERROR: permission denied for table car_area_imovel
sudo -u postgres psql -d iagro_sat -c "SET ROLE plat_tt601b_app; DELETE FROM plat_tt601b_acervo.public_car_area_imovel WHERE ogc_fid=1;"
#   ERROR: permission denied for view public_car_area_imovel
sudo -u postgres psql -d iagro_sat -c "SET ROLE plat_tt601b_app; SET plat.tenant_id='2'; EXPLAIN ANALYZE SELECT ogc_fid FROM plat_tt601b_acervo.public_car_area_imovel WHERE geom && ST_MakeEnvelope(-46.6,-23.6,-46.4,-23.4,4326) LIMIT 1000;"
#   One-Time Filter ... Index Scan ... (never executed) ... Execution Time: 0.817 ms
```

## Commits do ramo `wt/t601b`

- `516fae0` Publicacao sem copia do acervo: view so-leitura com porteiro de assinatura (item L6-01-b-view-so-leitura)
- `83306f3` Rotas da camada publicada entram nas guardas transversais: evento declarado e caso cruzado

## Estado da suíte (o que passa e o que já estava quebrado)

- `tests/api/test_acervo_publicacao.py` — 17 passed.
- `tests/unit` — 1 falha, `test_jobs_registro.py::test_tipos_de_prova_estao_registrados`
  (`ingestao.inspecionar: memoria_mb=768 fora de [128, 512]`). **Pré-existente**: falha igual com a árvore
  limpa (`git stash`), é o teto `PLAT_WORKER_MEMORIA_MB` da base de trilha.
- `make lint` (11 × `I001` em arquivos de teste alheios) e `make sem-marcador` (2 acertos em
  `app/geocodificador/motor.py` e `app/settings.py`) **já falham no master limpo** — conferido com `git stash`.
  Nenhum dos dois aponta arquivo meu.
- `tests/api/test_privilegios_declarados.py`, `test_docs.py`, `test_acervo.py`, `test_rls.py` — passam.
- `tests/api/test_eventos.py` e `tests/api/test_cruzado.py` — as rotas novas foram DECLARADAS nas duas guardas
  (commit `83306f3`) e saíram da lista de faltantes. As duas continuam vermelhas por causas alheias:
  `test_eventos` ainda tem 10 rotas sem evento (`/api/conexoes*`, `/api/importacoes*`, `/api/eu/foto`) e
  `test_cruzado` tem 13 rotas sem caso (`/api/importacoes*`, `/ogc/records*`, `metadado.xml`) mais um erro de
  preparação em `POST /api/papeis` ("operação fora do inquilino da sessão", `cruzado_casos.py:81`) que atinge
  TODAS as rotas parametrizadas, inclusive as que existem desde o turno 1.
- `tests/api/test_migracoes.py::test_tabela_reflete_os_arquivos_em_disco` — falha por deriva de ambiente: a base
  da trilha tem `048_smtp_convites_correcoes` e `049_convite_resolver_config` aplicadas, porque
  `laco/trilha_ambiente.sh` lê o DIRETÓRIO DE TRABALHO de `/home/dev/plataforma/enterprise`, onde essas duas
  ainda estão sem commit. A minha (`20260906T15521aa`) aparece dos dois lados, disco e banco.
- `tests/api/test_banco.py::test_conexao_tcp_como_plat_app` — o teste compara `current_user` com o literal
  `plat_app`; em qualquer base de trilha o papel é `plat_t<trilha>_app`. Falha em toda trilha, não só nesta.
- `tests/api/test_acervo_licenca.py` — o script de licença precisa de rede; erro de conexão, não de código.

## Risco de merge

- `app/main.py` (2 linhas, com a ordem do router explicada em comentário), `app/schema_ambiente.py` (4 linhas),
  `app/acervo/modelos.py` (append no fim), `MANUAL.md`/`ARQUITETURA.md`/`CHANGELOG.md` (blocos novos).
- `docs/openapi.json`: inserção pura (389 linhas, 0 remoção). **Quem for regerar o arquivo inteiro depois deve
  saber que o comitado já estava atrasado em relação ao master antes deste item.**
- ADR numerado `0018` porque `0015` e `0016` já estão tomados por trilhas não comitadas (`0016` está tomado
  DUAS vezes: `garage-por-inquilino` e `motor-amc-modelo-e-unidades`).
- Migração com carimbo `20260906T15521aa` (ADR 0014), conferida na hora — nenhum número reservado.

## Limpeza feita ao fim

`plat_tt601b`, `plat_trabalho_tt601b`, `plat_tt601b_acervo` e o schema de sondagem `zz_probe` foram
derrubados; os papéis `plat_tt601b_app`, `plat_tt601b_worker`, `plat_tt601b_acervo_publicador` e `zz_pub`
foram apagados depois de `REVOKE` explícito. O ACL de `public.car_area_imovel` voltou ao estado original
(`postgres`, `iagrosat_app`, `intel_157`, `tribuna_mig`), conferido depois. Ficaram no `pg_hba.conf` as duas
linhas que `trilha_ambiente.sh` acrescentou para os papéis da trilha; apontam para papéis que já não existem
(sem efeito) e não foram removidas para não mexer no arquivo enquanto outras trilhas rodam.

Quem for reproduzir precisa recriar a base: `bash laco/trilha_ambiente.sh t601b` e aplicar a migração à mão
(o passo está na seção "Como o adversário reproduz").
