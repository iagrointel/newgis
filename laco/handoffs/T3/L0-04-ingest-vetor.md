# L0-04-ingest-vetor — núcleo entregue (turno 3)

⚠ **Nota de commit**: por causa de `git commit` concorrente de outras duas trilhas no MESMO índice git
compartilhado (sem worktree isolado), o conteúdo deste item foi parar sob as mensagens de commit
`33e9d73` ("CHANGELOG: registra veredito do adversário independente para L0-02-e/f") e `331bb86`
("Corrige medidas de L0-02-tenant-auth.json após rodada contra openapi.json sujo") — nenhuma das duas fala
do L0-04. Confirmado que o conteúdo está certo (`git status`/`git diff` vazios contra o HEAD para todos os
arquivos deste item; os 20 testes passam rodando contra o HEAD atual). Não tentei corrigir a atribuição por
`reset`/`rebase` (proibido pelas regras de segurança do git desta sessão); registrado aqui para quem revisar
o histórico não estranhar a mensagem.

Objetivo · O que fiz · Evidência · Riscos · Pendências · Para o próximo papel (modelo de handoff do laço).

## Objetivo

Construir o NÚCLEO do item `L0-04-ingest-vetor` (ADR 0005): upload retomável no Garage (reaproveitado do
L0-11) → job de inspeção → confirmação do usuário → job de carga (`ogr2ogr` subprocesso, `PROMOTE_TO_MULTI`,
`ST_MakeValid`, `RLIMIT_DATA`/`OPENBLAS_NUM_THREADS=1`, `FORCE ROW LEVEL SECURITY`) → tabela
`d_<slug>.c_<uuid16>` → item de catálogo `camada_vetorial`. Escopo desta passagem: **4 formatos** (shapefile
zipado, GeoPackage, GeoJSON, CSV/TXT) e os **3 ataques** pedidos (shapefile sem `.prj`, GeoJSON com polígono
auto-intersectado, CSV com vírgula decimal).

## O que fiz

**Migrações** (`db/migracoes/`, aplicadas diretamente via `psql` quando `sudo bash db/migrar.sh` não pôde
rodar por causa de um arquivo divergente de OUTRA trilha em andamento — nunca editei o arquivo dela nem toquei
em migrações de outra trilha):
- `029_ingestao_vetor.sql`: `plat.importacao` (RLS, estado final imutável), `plat.tenant.uso_bytes`/
  `uso_reservado_bytes`, role `plat_leitor`, `plat.camada_schema_garantir`/`plat.camada_preparar` (SECURITY
  DEFINER), `plat.feicao_inserir`/`plat.feicao_versao` (gatilhos genéricos de toda tabela de camada),
  `tenant_criar` passa a criar o schema `d_<slug>` do inquilino novo (+ backfill dos 3 já existentes),
  `tipo_item.camada_vetorial` ganha esquema v2 (`estatisticas`/`importacao`), eventos novos.
- `032_ingestao_arquivo_cascade.sql`: **correção pedida por outra trilha (L5-05)** — `plat.importacao.
  arquivo_id` ganhou `ON DELETE CASCADE` (a FK sem cláusula quebrava o teardown compartilhado
  `_expurgar_zt` de `tests/api/catalogo/conftest.py` sempre que um item `arquivo` de teste tinha uma
  importação vinculada). Decisão registrada no próprio arquivo: CASCADE, não SET NULL — a proveniência que
  importa sobrevive em `plat.item.dados.procedencia`/`dados.importacao` da CAMADA, não em `plat.importacao`.
- `033_ingestao_funcoes_privilegios.sql`: **correção pedida pelo testador** (`test_eventos_e_seguranca.py::
  test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app`) — as funções da 029 nasceram com
  `EXECUTE` para `PUBLIC` (a instalação não herda `PUBLIC` fechado só pelo `ALTER DEFAULT PRIVILEGES`; o
  padrão da casa é `REVOKE EXECUTE ... FROM PUBLIC` explícito depois de `CREATE FUNCTION`, igual a
  `010_jobs_gatilhos_execute.sql`/`016_catalogo_apagar_usuario.sql`). Gatilhos puros (`feicao_inserir`,
  `feicao_versao`, `importacao_estado_final_imutavel`) fecham para `PUBLIC, plat_app`; as duas chamadas
  diretamente pelo Python (`camada_schema_garantir`, `camada_preparar`) fecham só `PUBLIC`.

**Código** (`app/ingestao/`, novo):
- `nomes.py` — normalização de nome de campo/tabela (ADR seção 8): minúsculo, sem acento, `[a-z0-9_]`,
  ≤ 63 bytes, palavra reservada/coluna obrigatória com sufixo, duplicata com `_2`/`_3`.
- `formatos.py` — tipo declarado × conteúdo (zip com trio `.shp`, cabeçalho SQLite do gpkg, `{`+`"type"` do
  geojson), conferência de zip-bomba (entradas, razão, caminho, symlink, aninhado) ANTES de extrair.
- `csv_normalizar.py` — separador `,`/`;`/tab, vírgula decimal → ponto, BOM/charset, coluna de coordenada
  por nome; entrega um CSV canônico que o GDAL lê sem ambiguidade.
- `geometria.py` — resolução do tipo (um só tipo → ele; Polygon+MultiPolygon → Multi; mistura de família →
  pergunta).
- `tipos_campo.py` — mapa OGR → PostgreSQL e promoções de tipo oferecidas na tela.
- `inspecionar.py` — job `ingestao.inspecionar`: baixa o objeto, roda `ogrinfo`/sondas, grava a proposta.
- `carregar.py` — job `ingestao.carregar`: cota, `ogr2ogr` (`PROMOTE_TO_MULTI`), `ST_MakeValid` (ordem
  corrigida — ver Riscos), `plat.camada_preparar`, estatísticas, item de catálogo + relação + evento;
  qualquer falha faz `DROP TABLE` + `DELETE` do item (nunca sobra órfão dos dois lados).
- `rotas.py` — `POST /api/importacoes {arquivo_id, formato}` (o `tipo_declarado` do ADR entra aqui, não no
  upload genérico do L0-11 — ver Pendências), `GET /api/importacoes[/{id}]`, `PUT .../confirmar`, `DELETE`,
  `GET /api/importacoes/formatos`.

**Testes**: `tests/dados/gerar.py` (dado aberto REAL: recorta `web/dados/basemap/guarulhos.pmtiles`, já no
repositório — cobertura do solo e lugares do OSM de Guarulhos — via `ogr2ogr`, sem baixar nada novo, ~150 KB
no total) gera os fixtures em `tests/dados/gerados/` (no `.gitignore` agora); `tests/unit/test_nomes.py` (7
testes); `tests/api/ingestao/` (13 testes: 4 formatos + os 3 ataques pedidos + RLS cruzada + duas importações
paralelas do mesmo arquivo + cota excedida sem tabela órfã + CRS confirmado nunca reprojetado).

## Evidência (comando + saída literal)

```
$ venv/bin/pytest tests/api/ingestao tests/unit/test_nomes.py -q -m "not lento"
....................                                                     [100%]
20 passed
```

Verificação direta da correção de FK pedida pela L5-05 (reprodução do sintoma relatado, dentro de uma
transação com ROLLBACK — nada ficou no banco):
```sql
INSERT INTO plat.item(...) tipo='arquivo' ...;
INSERT INTO plat.importacao(...) arquivo_id=<esse item>...;
SELECT plat.item_lixeira(id, true);
SELECT plat.item_expurgar(id);   -- antes: ForeignKeyViolation; agora: t (sucesso)
SELECT count(*) FROM plat.importacao WHERE arquivo_id=<esse item>;  -- 0 (cascade)
```

Verificação da correção de privilégio pedida pelo testador:
```
$ pytest tests/api/catalogo/test_eventos_e_seguranca.py::test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app -q
FAILED antes (10 funções minhas na lista) -> depois: só sobram tg_conexao_atualizado_em/amc_* (de outra trilha, fora do meu escopo)
```

Exemplo real medido (shapefile sem `.prj`, ataque do item pai): 80 feições de cobertura do solo de Guarulhos,
`crs.origem="nenhum"`, `crs.sugestao=4674` (extent dentro do Brasil), `perguntas=["crs"]`; confirmar sem
responder devolve `422 perguntas_pendentes`; confirmar com `{"crs":{"srid":4674}}` carrega as 80 feições.
GeoJSON com polígono auto-intersectado ("gravata"): `validade.invalidas=1`, `validade.exemplo` cita
`Self-intersection`; depois da carga, `relatorio.corrigidas=1`, `relatorio.descartadas=0`. CSV com `;` e
vírgula decimal (dado real de lugares de Guarulhos): valor de latitude gravado bate byte a byte com o CSV de
origem convertido manualmente no teste.

## Riscos

- **Bug real encontrado e corrigido**: a ordem `ST_MakeValid(ST_ReducePrecision(geom, 1e-9))` (como o ADR
  0005 seção 6.4 escreve literalmente) QUEBRA em geometria de verdade — GEOS lança `TopologyException:
  unable to assign free hole to a shell` tentando arredondar coordenadas de um polígono AINDA inválido
  (medido com duas feições reais de cobertura do solo de Guarulhos, buraco tocando o contorno). A ordem
  certa, usada em `app/ingestao/carregar.py`, é `ST_ReducePrecision(ST_MakeValid(geom), 1e-9)` — validar
  primeiro, reduzir precisão do resultado já válido depois. Vale registrar essa correção se o ADR 0005 for
  revisado por outra trilha.
- `-nlt <tipo singular>` (Polygon/LineString) trava quando `ST_MakeValid` fragmenta a geometria em várias
  partes (`Geometry type (MultiPolygon) does not match column type (Polygon)`) — por isso a carga usa
  `PROMOTE_TO_MULTI` (pedido explícito do dono) sempre que a família não é genérica, e lê o tipo REAL da
  coluna em `geometry_columns` depois do `ogr2ogr` (nunca confia no tipo pré-resolvido da proposta para as
  contas de dimensão/estatística).
- `tenant.cota_bytes` é **compartilhado** entre a cota do bucket do Garage (L0-11) e a cota de armazenamento
  de tabela desta trilha — mexer nele em teste automatizado sob concorrência derrubou o upload de outra
  suíte (MEDIDO: a cota do bucket do Garage do inquilino `demo` ficou travada em 1 byte depois de uma
  corrida). O teste de cota (`test_cota_excedida_nao_cria_tabela`) foi reescrito para mexer só em
  `uso_reservado_bytes` (nunca em `cota_bytes`). Se outro item também testar cota via `cota_bytes` do
  inquilino `demo`/`demo2`, o mesmo risco existe — considerar um terceiro inquilino de teste dedicado a
  cota, ou uma cota SEPARADA para tabela × bucket.
- Migração numerada em produção sem `sudo bash db/migrar.sh` completo (por causa do arquivo divergente de
  outra trilha): apliquei 029/032/033 manualmente com o MESMO mecanismo do script (sha256 + INSERT em
  `plat.versao_migracao` na mesma transação do SQL), conferido por consulta direta depois de cada uma. Vale
  rodar `sudo bash db/migrar.sh` inteiro assim que a trilha do 030 resolver a divergência, só para confirmar
  que bate tudo.

## Pendências (fora do escopo desta passagem — o que falta para o item PAI fechar)

Por sub-item do ADR 0005:

- **L0-04-a (upload)**: reaproveitei o `POST /api/arquivos` genérico do L0-11 (corpo cru, sem multipart real
  em partes do lado do cliente) em vez do protocolo de partes de 16 MiB do ADR seção 3 — o L0-11 já faz
  streaming/multipart real do LADO DO SERVIDOR para o Garage, mas o cliente manda o arquivo inteiro numa
  chamada. O `tipo_declarado × conteúdo` do ADR (seção 3.3) ficou em `POST /api/importacoes {formato}`, não
  em `POST /api/arquivos` — documentado no topo de `app/ingestao/rotas.py`. Falta: retomada de upload
  interrompido (partes fora de ordem, reenvio), zip-bomba com 1 milhão de entradas geradas de verdade
  (testei só a lógica em `formatos.conferir_zip`, não um ataque de 1M entradas reais), cota ANTES do
  primeiro byte.
- **L0-04-b (inspeção)**: feito para os 4 formatos. Falta: `.txt`/`.tsv` genérico (só testei `.csv`), CSV com
  300 colunas/0 linhas, `.dbf` de 4 GB, GeoJSON de 1 feição com 10 milhões de vértices (o teto
  `FEICAO_BYTES_MAX` do ADR não foi implementado nesta passagem — nenhum arquivo de teste o dispara).
- **L0-04-c (carga)**: feito o núcleo (RLS FORCE, colunas obrigatórias, `ST_MakeValid` com relatório,
  invariante tabela↔item). Falta: teste automatizado de morte do worker no meio (SIGKILL) — confirmei só
  manualmente que a lógica de limpeza roda (`_limpar_orfao`), não escrevi o teste com `tests/jobs_sessao.py`
  que mata o processo de verdade.
- **L0-04-d completo**: faltam KML/KMZ, GPX, XLSX/XLS/ODS (o ADR já desenha as regras nas seções 10-11).
- **L0-04-e (DXF/DWG)**, **L0-04-f (FileGDB/FlatGeobuf/GML/MapInfo/GeoParquet)**: nada construído; o ADR já
  tem a análise (GeoParquet precisa de `pyogrio`, ausente na venv; DWG precisa de decisão D23/ODA).
- **L0-04-g (atualizar dados)**, **L0-04-h (exportação)**, **L0-04-i (fonte registrada/postgres_fdw)**,
  **L0-04-j (vista de camada)**: nada construído.
- **Função de tile** (`d_<slug>.tile_<uuid16>`, C3 do L2) e `plat.contexto_por_token` (stub): NÃO criados
  nesta passagem — são gancho explícito para L2-01/L2-04, não fazem falta para o portão deste turno.
  `plat.camada_apagar(schema, tabela)` também não foi criado (o destruidor já cai no `DROP TABLE` genérico
  quando a função não existe — comportamento correto e já testado; só falta se uma VISTA depender da
  camada, que é o L0-04-j).
- **Georreferência/Helmert (DXF)**, **fuso horário de `DateTime` sem deslocamento**, **Z/M**: não se aplicam
  aos 4 formatos desta passagem (nenhum teve DXF nem coluna DateTime sem fuso).

## Para o próximo papel

Quem pegar `L0-04-d-formatos-base` (completar KML/GPX/XLSX): os `PREPARADORES` em `app/ingestao/
inspecionar.py` já são um dicionário extensível (`{"shapefile.zip": ..., "gpkg": ..., ...}`) — acrescentar
uma entrada por formato é o padrão a seguir; `_ogrinfo_json`/`_amostra_validade`/`_tipos_por_varredura` são
genéricos e não precisam mudar. Quem pegar `L0-04-c` completo (teste de morte do worker): reusar
`tests/jobs_sessao.py` (já existe na casa) e o padrão de `test_orfaos.py` do ADR seção 19.2 (ainda não
escrito — só o teste de cota+RLS cobre parte da invariante nesta passagem).
