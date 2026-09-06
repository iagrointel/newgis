# L0 fundação — decisões de conceito (05/09/2026)

Linha: **L0 fundação** (inquilinos, identidade e SSO, catálogo/conteúdo/metadado, ingestão vetorial, fila de jobs,
backup e status, administração da organização, cotas, grupos, compartilhamento, favoritos, lixeira, dependências,
auditoria). Itens em `L0.json` (58 novos, filhos dos 9 existentes mais 5 de topo). Este documento fixa o que, se
errado, obriga a refazer. Cada decisão traz opções, custo de mudar depois, recomendação com motivo MEDIDO nesta máquina
(comando indicado), LIDO em código que já roda aqui (só leitura) ou DOCUMENTO OFICIAL (URL testada por HTTP em
05/09/2026, código 200 no próprio endereço; anexo A), e o que obriga nas outras linhas.

Contexto fixo (ADR 0001, aceito): schema `plat`, role `plat_app` sem BYPASSRLS, RLS `FOR ALL USING/WITH CHECK` em toda
tabela com `tenant_id`, `plat.tenant_atual()`/`usuario_atual()` por `set_config` local, migrações `NNN_*.sql`
imutáveis por sha256, FastAPI + psycopg2 síncrono com pool de reconexão, módulos ES sem bundler, `/saude` e OpenAPI
comitado. Nada abaixo contradiz o ADR; onde estende, diz.

Medições de base (05/09/2026): PostgreSQL 16.13 + PostGIS 3.6.3 (`SELECT version()`); extensões instaladas em
`iagro_sat`: pgcrypto 1.3, unaccent 1.1, pg_trgm 1.6, postgres_fdw 1.1, btree_gist, citext, hstore, timescaledb 2.26.4;
disponíveis e não instaladas: ltree 1.2, uuid-ossp, postgis_raster, file_fdw (`pg_available_extensions`);
`wal_level=replica`, `archive_mode=off`, `max_wal_senders=10`; GDAL 3.8.4 com drivers ESRI Shapefile, GPKG, GeoJSON,
GeoJSONSeq, LIBKML/KML, CSV, GPX, XLSX/XLS/ODS, DXF, CAD (leitura), OpenFileGDB, FlatGeobuf, GML/GMLAS, MapInfo,
SQLite, MVT, PMTiles, PostgreSQL, OSM, WFS, OAPIF, ESRIJSON, TopoJSON; **sem driver Parquet/Arrow** (`ogrinfo --formats`);
venv do repositório: lxml 6.1.1, pyproj 3.7.2, shapely 2.1.2, rasterio 1.5.0, pystac 1.14.3, jinja2, httpx, PIL 12.2,
qrcode, pydantic 2.13.4, fastapi 0.138.0 presentes; **ausentes**: ezdxf, pyotp, authlib, python3-saml, pysaml2,
procrastinate, ldap3, aiosmtpd, xmlschema, psycopg 3, fiona, python-multipart; binários ausentes: pgbackrest, rclone,
xmlsec1, xmllint, clamscan, LibreDWG (existe só no GPU box, LIDO no roundtrip do SIG de teste interno), ODA;
presentes: docker, mc, pg_dump, pg_basebackup, tesseract, tippecanoe (`~/tools`); Garage 2.3.0 ativo em :3900
(admin :3903, `replication_factor = 1`, serviço `plataforma-garage`); disco `/` 98 % (13 GB livres) e `/mnt/pgdata`
98 % (17 GB); RAM 23 GB com 3 GB disponíveis.

---

## D1. Identificador de item, grupo, job e arquivo: UUID opaco, gerado no banco, estável para sempre

Opções: (a) `serial` interno exposto na URL (o que tenant/usuario usam no ADR); (b) UUID v4 por `gen_random_uuid()`
(pgcrypto, já instalado; o SIG de teste interno já tem `uid uuid` em toda tabela de ontologia); (c) id curto de 16 hex
como o item Esri (32 hex).

Custo de mudar depois: alto. O id vai para URL pública, para o JSON de mapas/apps (referências entre itens), para o
pacote de exportação do inquilino, para o link compartilhado e para o conector Esri (L2-08 clona itens preservando
ids). Trocar depois é reescrever toda referência guardada em `dados jsonb`.

Recomendação: (b). Motivo documentado: a irritação nº 1 do usuário Esri ao migrar é o id de item e a URL gravados
dentro do JSON dos mapas (handoff `21_esri.md`, fontes COM-urlchange, KB-itemid, E12-migrategroup); a exportação de
grupo da Esri existe para "manter os IDs". UUID é opaco, independente de host, gerado sem coordenação (importação de
pacote preserva o id sem conflito) e não enumerável (o serial permitiria varrer `/api/itens/1..N`). `serial` continua
em tenant, usuario, sessao, token (chaves internas, nunca expostas fora do inquilino). Regra: referência entre itens é
sempre pelo UUID, nunca por URL absoluta; a URL pública é derivada do UUID.

Obriga: L2 (mapa/app guardam `camadas: [uuid]`), L5 (construtores), L6 (conectores geram UUID determinístico a partir
do id de origem: `uuid5(namespace_inquilino, id_origem)` para reimportar sem duplicar), L7-08 (SDK).

## D2. Modelo do catálogo: uma tabela `item` genérica + registro de tipos com JSON Schema + tabelas específicas por família

Opções: (a) uma tabela por tipo (mapa, camada, app, painel…); (b) uma tabela `item` com `tipo` e `dados jsonb`,
mais tabela específica só onde há dado físico (camada → tabela PostGIS; raster → STAC; arquivo → objeto); (c) só jsonb.

Custo de mudar: alto para (a) → (b) (migração de N tabelas e de toda rota); baixo para (b) → acrescentar tabela
específica.

Recomendação: (b), com `plat.tipo_item` (nome, família ∈ {mapa, camada, raster, app, painel, formulário, fluxo, rede,
arquivo, ferramenta, documento}, JSON Schema de `dados`, ícone, módulo do front que abre o item). Motivo: a Esri tem
cerca de 150 tipos em 6 famílias (DEV-itemtypes) e o Portal os trata em uma só tabela lógica com `type` +
`typeKeywords`; o GeoServer separa workspace/store/layer porque só serve dado, não apps. Uma tabela permite busca,
compartilhamento, lixeira, dependências, versões e favoritos escritos uma vez para todos os tipos; o JSON Schema por
tipo dá validação (422 com caminho) sem migração quando L1-L5 criam tipo novo. Nomes dos campos do item seguem os
nomes REST da Esri traduzidos (título, resumo=snippet, descrição, tags, créditos=accessInformation, termos=licenseInfo,
extent, categorias, status=contentStatus, protegido=protected, pasta=ownerFolder) para baratear o conector L2-08/L6.

Obriga: toda linha registra seu tipo em `tipo_item` na migração do próprio item, com o JSON Schema; o front expõe o
módulo de abertura pelo nome do tipo.

## D3. Onde vive o dado vetorial do inquilino: schema por inquilino, tabela por camada, `tenant_id` + RLS em toda tabela

Opções: (a) uma tabela genérica `feicao (item_id, atributos jsonb, geom)` para tudo; (b) schema por inquilino
`d_<slug>` com uma tabela por camada `c_<uuid16>`, colunas tipadas, `tenant_id` com `DEFAULT plat.tenant_atual()` e a
mesma política de RLS das tabelas de catálogo; (c) igual a (b) sem `tenant_id`, confiando no `search_path` por
requisição.

Custo de mudar: muito alto (reescrever cada tabela de camada e todo serviço que lê: Martin, tipg/FeatureServer,
exportação, geoprocessamento).

Recomendação: (b). Motivos: MEDIDO na casa (DOC.md 17.2) que o banco desta máquina sustenta 1.467 tabelas e 138
milhões de feições com consulta de mapa em 20 ms; colunas tipadas são o que o FeatureServer (L2-04), o QGIS/Pro por
query layer (DOC.md 22: "o Pro lê o nosso PostgreSQL sem Enterprise") e o `ogr2ogr` esperam, e (a) perde índice por
campo, tipos e estatísticas. `tenant_id` + RLS em cada tabela de camada cumpre o portão P6 ao pé da letra ("RLS em toda
tabela com tenant_id"), mantém a defesa em profundidade quando um serviço lê o banco sem passar pela API (Martin,
tipg) e custa 4 bytes por linha mais uma política por tabela (barato). Schema por inquilino dá `pg_dump -n d_<slug>`
(backup e exportação por inquilino, D15), medição de cota por `pg_total_relation_size` (L0-07-c) e apagamento limpo
ao encerrar o inquilino. Convenções: `fid bigserial`, `geom geometry(<Tipo>, <srid>)` tipada, campos saneados
(minúsculo, sem acento, ≤ 63 bytes, mapa original→novo guardado no item), colunas de rastreio de edição
(`criado_em/atualizado_em/criado_por/atualizado_por`) desde a criação porque L2-03 e L2-13 dependem delas, `GIST`
sempre. Vistas de camada (L0-04-j) são `VIEW ... WITH (security_barrier)` no mesmo schema. Regra da casa mantida:
`ST_MakeValid` + `ST_ReducePrecision` na entrada, com relatório.

Obriga: L2-01/L2-04 leem só via role com contexto (`plat.contexto_por_token`); L2-03 escreve pela mesma RLS; L3 e L2-05
criam resultado como camada nova no mesmo padrão; L4 cria as tabelas de rede com as mesmas colunas de base; L7-09 mede
a cota pelo schema.

## D4. CRS de armazenamento: o do arquivo quando tem código EPSG; sem CRS, pergunta com sugestão SIRGAS 2000 (EPSG:4674); extent do item sempre em EPSG:4326

Opções: (a) reprojetar tudo para Web Mercator 3857 como a Esri faz nas camadas hospedadas publicadas do portal
("The features are published in the WGS 1984 Web Mercator (Auxiliary Sphere) coordinate system", E11-publishfeat);
(b) reprojetar tudo para 4674; (c) guardar no CRS de origem quando reconhecido, exigir escolha quando não.

Custo de mudar: muito alto (reprojetar todas as tabelas; medições de área/comprimento mudam).

Recomendação: (c). Motivos: DOCUMENTO: SIRGAS 2000 é o sistema geodésico oficial do Brasil (IBGE RPR 01/2015) e
EPSG:4674/UTM 31981-31985 é o que o dado brasileiro chega; reprojetar para 3857 na entrada destrói precisão métrica
(o SIG de teste interno trabalha em 31982 métrico por isso, LIDO em `schema.sql`). Martin e TiTiler reprojetam para o
tile na saída; o FeatureServer devolve no `outSR` pedido; QGIS/Pro leem o SRID nativo. Regra do portão do item pai:
"CRS errado/ausente é perguntado, não assumido" — a inspeção (L0-04-b) sugere 4674 quando os valores estão em graus
dentro do Brasil e 3197x/3198x quando em metros, mas o usuário confirma. O extent do item fica em 4326 (como o `extent`
REST da Esri) para filtro espacial na busca e no catálogo externo. Comprimento e área sempre por `geography`
(regra da casa: comprimento geodésico, CRS explícito em toda comparação).

Obriga: L2-02 (rótulos de unidade), L2-05 (geoprocessamento declara o CRS de cálculo), L3 (grade em CRS métrico
declarado), L6 (conectores registram o CRS de origem no bloco de procedência).

## D5. Identidade: 4 perfis do ADR como tipo de usuário + privilégios finos com vocabulário fechado + papéis personalizados

Opções: (a) só os 4 perfis (admin, editor, visualizador, campo) com `if perfil == 'admin'` espalhado; (b) privilégios
finos (≈ 40 nomes) em tabela, papéis padrão fixos e papéis personalizados por inquilino, tipo de usuário como teto;
(c) ACL por objeto no estilo do GeoServer ACL/GeoFence.

Custo de mudar: médio-alto ((a) → (b) obriga a revisitar toda rota; (b) → (c) é só acrescentar regra por item, que já
existe como compartilhamento).

Recomendação: (b), implementado a partir do L0-07-b, mas com a função `plat.tem(privilegio)` já usada por L0-02/L0-03
com um mapa fixo perfil→privilégios (migração posterior só preenche a tabela). Motivos: DOCUMENTO: a Esri separa
tipo de usuário (teto), papel (5 fixos ou personalizado) e cerca de 70 privilégios gerais e administrativos
(E11-usertypes, E11-roles, E11-priv); o usuário que migra espera "Member roles > Create role". Sem assento nem
licença por membro (regra da spec: taxímetro de TB, sem crédito nem assento); o "tipo" vale só como teto de
privilégios e como contagem para relatório. Regras copiadas da Esri e testáveis: pelo menos um administrador; só
administrador altera administrador; papel com privilégio administrativo só para tipo criador; não se rebaixa tipo de
quem possui conteúdo.

Obriga: toda rota declara o privilégio exigido (teste percorre o OpenAPI e reprova rota sem privilégio); L2-03
(feições.editar × editar_total), L2-07 (campo), L5 (publicar app), L7-08 (tokens.gerar, webhooks.gerir).

## D6. Sessão, senha, 2FA e token: números declarados

Decisão (números que o testador mede, com a fonte que os ancora):

| grandeza | valor | ancora |
|---|---|---|
| sessão | expira 12 h sem uso; 7 dias no máximo; cookie HttpOnly, Secure, SameSite=Lax; só hash no banco | ADR 0001 seção 6; token Esri padrão 120 min, máximo 14 d (E11-tokenexp) |
| senha | ≥ 10 caracteres com letra e número; ≠ login; sem reutilizar as 5 últimas; expiração opcional por inquilino | LIDO em `novo_inquilino.py` do SIG de teste interno (10 + dígito); Esri ≥ 8 com letra e número (E11-security) |
| hash | pbkdf2_sha256, 600.000 iterações, biblioteca padrão | ADR 0001; OWASP Password Storage |
| bloqueio | 5 falhas em 15 min → 15 min; configurável; por usuário, nunca por inquilino | padrão Esri (E11-security) |
| 2FA | TOTP RFC 6238, SHA-1, 30 s, janela ±1, 8 códigos de recuperação; 5 códigos errados = 15 min; admin desliga; exigir para todos = opção do inquilino | E11-security (11.4 não obriga; 12.1 tem Enforce) |
| token de serviço | escopos fechados; padrão 90 d; máximo 365 d; Referer/IP; 2 tokens válidos por 24 h na rotação; motivo legível no 401 | chave de API Esri ≤ 1 ano, 2 chaves, referrers (DEV-apikey); E12-limitusage |
| link compartilhado | ≥ 32 hex; validade opcional; revogável; contagem de acessos | irritação 8 (Invalid Token) |

Custo de mudar: baixo (constantes em `app/limites.py` + `tenant.config`), desde que existam. O que não pode mudar
sem migração: hash de sessão (já decidido) e formato do hash de senha (versão no prefixo `pbkdf2_sha256$`).

Obriga: L1-02 usa o mesmo `token_servico` com escopo `tiles:ler`; L7-03 não redefine limiares, só os testa.

## D7. Compartilhamento: 5 níveis, "público" só com o inquilino autorizando, e acesso decidido por função usada na RLS

Opções: (a) só privado/grupo/inquilino/link (hipótese do item L0-03); (b) mais público anônimo, padrão desligado por
inquilino (D24 do dono); (c) ACL por usuário e por item.

Recomendação: (b). Motivos: a Esri tem Owner/Organization/Everyone/grupos (E11-share) e o usuário migrado tem mapas
públicos; o catálogo externo (OGC Records/CSW, L0-09-d) e o Hub (L5) precisam de "público"; mas o padrão da casa é
`noindex` e link não adivinhável, logo público exige ato do admin do inquilino. A decisão do que é visível fica em
`plat.pode_ler(item_id)` / `pode_editar` (padrão da função `pode()` do SIG de teste interno, LIDO em `schema.sql`),
usada nas políticas de RLS de `item` e das tabelas dependentes, para que Martin/tipg e a API decidam igual. Regra
tirada da irritação 2: compartilhar um mapa mostra a árvore de dependências (D9) com o nível de cada camada e oferece
"elevar ao nível do mapa" como escolha; nunca rebaixa nem eleva em silêncio. 404 (não 403) para item sem acesso, para
não confirmar existência. Link revogado nega em ≤ 1 s (refutação do item pai): sem cache de autorização.

Custo de mudar: médio (a função é uma; as políticas apontam para ela).

Obriga: L2-01 (lista de camadas do mapa filtra pelo `pode_ler`), L5 (publicar app = compartilhar item), L7-12
(classificação "pessoal" bloqueia público).

## D8. Busca: PostgreSQL FTS com pesos e trigram, índice na mesma transação; sem motor externo

Opções: (a) `ILIKE` em título e tags; (b) `tsvector` gerado (A título, B tags, C resumo, D descrição; `portuguese` +
`unaccent`) com `pg_trgm` para prefixo/erro de digitação e sintaxe por campo; (c) Meilisearch/OpenSearch.

Recomendação: (b). Motivos: MEDIDO: `unaccent` e `pg_trgm` já instalados; 3 GB de RAM disponíveis descartam (c);
DOCUMENTO: a busca simples da Esri só olha título e tags e o usuário reclama que o item cujo nome bate não vem
primeiro (irritação 9, E11-search, COM-searchidea) — o peso A no título resolve; a busca avançada da Esri
(E12-advsearch) tem sintaxe por campo e operadores, que reproduzimos por gramática própria (não se passa texto do
usuário direto ao `to_tsquery`). Coluna gerada `STORED` garante índice atualizado na mesma transação da edição (a Esri
tem indexador separado, DEV-indexer, e tags por API "não aparecem").

Custo de mudar: baixo (coluna + índice + uma função de consulta).

Obriga: L6-01 indexa o acervo com o mesmo vocabulário de campos; L7-10 acrescenta configuração `english/spanish`
por inquilino.

## D9. Dependências entre itens: tabela de relações com vocabulário fechado, gravada por quem cria o vínculo, sem inferência

Opções: (a) inferir dependências lendo o JSON dos mapas na hora; (b) `plat.item_relacao(origem, destino, tipo)` gravada
na mesma transação em que o item de origem salva sua configuração; (c) grafo externo.

Recomendação: (b). Motivos: DOCUMENTO: a Esri tem 45 tipos de relação REST (DEV-relationships) e a interface só
mostra as de camada hospedada; o usuário sente a "ordem de exclusão" e a sobrescrita que quebra mapas (irritações 6 e
7). Uma tabela com FK `ON DELETE CASCADE` e índice em `destino` dá "usado por" em < 50 ms, ordem topológica de
exclusão, aviso antes de sobrescrever e árvore ao compartilhar. Vocabulário inicial: camada_de_mapa, dado_de_camada,
mapa_de_app, vista_de_camada, estilo_de_camada, arquivo_de_camada, formulario_de_camada, resultado_de_job,
anexo_de_item, fator_de_motor, rede_de_camada. Ciclo é recusado no INSERT.

Custo de mudar: baixo (vocabulário cresce por migração de uma linha).

Obriga: L2-01 (mapa grava camada_de_mapa ao salvar), L2-02 (estilo), L3 (fator_de_motor), L4 (rede_de_camada), L5
(mapa_de_app), L1 (dado_de_camada aponta para o item STAC).

## D10. Lixeira, proteção, status e versões de item: exclusão lógica com 30 dias, versão a cada PUT

Opções: (a) apagar de verdade como o Enterprise (KB-recover: "Recycle Bin não é suportado"); (b) lixeira de 14 dias
como o ArcGIS Online (DEV-recyclebin); (c) lixeira de 30 dias por inquilino + versões de configuração por item.

Recomendação: (c). Motivos: irritação 5 ("apagou, perdeu; só webgisdr") e 6 (item preso); o custo é um campo
`apagado_em` e um periódico; a tabela física da camada só é apagada no expurgo, o que também protege o job de
importação que falhou no meio. Versões (L0-03-l) usam o `historico` antes/depois (padrão `fn_historico` do SIG de
teste interno, LIDO) e não existem no Enterprise (registrado como "não encontrado na doc"). A lixeira conta na cota
(refutação de L0-07-c).

Custo de mudar: baixo.

Obriga: toda consulta de catálogo filtra `apagado_em IS NULL` pela política de RLS (não por cada rota); L7-12 define
retenção por classificação.

## D11. Ingestão vetorial: GDAL por subprocesso no worker, nunca no processo da API; inspeção antes de criar tabela; formatos por driver medido

Opções: (a) fiona/pyogrio no processo da API; (b) `ogrinfo -json` + `ogr2ogr` por subprocesso em job (L0-05), com
limite de memória do worker; (c) GeoServer Importer como serviço (GS-importer).

Recomendação: (b). Motivos: MEDIDO: GDAL 3.8.4 do sistema tem todos os drivers do portão (shapefile, GPKG, GeoJSON,
KML, CSV, GPX, XLSX, DXF, OpenFileGDB, FlatGeobuf, GML) menos Parquet; fiona não está na venv; um upload de 2 GiB
no processo da API derruba os 2 workers (MemoryMax 1 GB no ADR); o worker tem o próprio limite. O importador do
GeoServer (GS-importer-formats) cobre shapefile, GeoTIFF, CSV, KML, GPKG e bancos, mas exige Java e configuração de
workspace; não entra na pilha. GeoParquet: ler por DuckDB spatial (já usado na casa, DOC.md 17.2) até haver libgdal
com Arrow; decisão de instalação fica com o gerente do item. DWG: LibreDWG fora do processo web (GPL, já roda no GPU
box para o SIG de teste interno) ou ODA (D23). Regras: inspecionar primeiro e devolver proposta editável; CRS
ausente pergunta (D4); codificação do shapefile pelo `.cpg` ou pergunta; CSV com vírgula decimal e `;` reconhecidos
(comportamento que a Esri só tem parcialmente: "fields can be separated with a comma, semicolon, or tab", E11-csvgpx);
fuso horário das datas escolhido (a Esri assume UTC); tabela sem geometria é tipo "tabela"; endereço sem coordenada
vai para L2-11-a.

Custo de mudar: médio (a interface de proposta/confirmação é o contrato; o motor por trás é substituível).

Obriga: L1-01 segue o mesmo padrão (inspeção → job → item); L2-08 (migração AGOL) importa camadas hospedadas pelo
mesmo caminho (GeoJSON/FGDB exportados); L6-02 (conectores vivos) cria "camada referenciada" sem copiar.

## D12. Fila de jobs: própria, só com Postgres (SKIP LOCKED + LISTEN/NOTIFY + heartbeat), Procrastinate como reserva documentada

Opções: (a) `BackgroundTasks` do FastAPI (o que o SIG de teste interno faz, LIDO em `app/v2.py`: o job morre com o
processo); (b) Procrastinate (PROC: Python 3.10+, PostgreSQL 13+, retentativa, periódicos, locks, cancelamento antes
de iniciar e abort cooperativo, esquema próprio com migrações); (c) fila própria: tabela `plat.job` com `FOR UPDATE
SKIP LOCKED`, `NOTIFY` para acordar, heartbeat de 10 s, ceifador de órfãos em 60 s, retentativa 3× com espera
2·4·8 s, lock por chave, cancelamento cooperativo + SIGTERM em 30 s, periódicos por cron; (d) Redis/Celery.

Recomendação: (c). Motivos: MEDIDO: Procrastinate não está instalado e seu conector síncrono é psycopg 3 (também
ausente), enquanto o ADR fixa psycopg2 com pool de reconexão; (d) traz um serviço a mais numa máquina com 3 GB livres;
a semântica que o portão pede (progresso em tempo real, cancelar, sobreviver a reinício, 1 worker com limite de RAM,
tela por inquilino) é exatamente a que a doc do Procrastinate descreve (PROC-cancel: cancela só antes de iniciar;
abort é cooperativo; PROC-locks; PROC-cron) e cabe em ~300 linhas sobre o pool existente, com RLS por `tenant_id`
(Procrastinate não tem inquilino). A máquina de estados segue a do job de geoprocessamento da Esri traduzida
(DEV-gpjob: Submitted, Waiting, Executing, Cancelling, Cancelled, Failed, TimedOut, Succeeded) para que L2-05 e L5-02
exponham o mesmo vocabulário no `/svc/` Esri-compatível. Se a fila própria reprovar o teste de morte duas vezes
(SIGKILL no meio: job nunca aparece "concluído"), o item L0-05-a troca por Procrastinate com psycopg 3 só no worker —
custo escrito: uma dependência nova e um esquema a mais.

Custo de mudar: médio (o contrato de tarefa `@tarefa(nome, timeout, memoria)` e a tabela vista pela tela são os
mesmos; muda o motor).

Obriga: L1-01 (COG), L2-05 (geoprocessamento), L3 (motor), L5-02 (fluxos), L1-05 (IA no GPU box: job com executor
remoto), L7-06 (métrica da fila): tudo é job desta fila; nenhum item cria thread ou `BackgroundTasks` para trabalho
que dure mais de 1 s.

## D13. Objetos: Garage já ativo, 1 bucket por inquilino, nomes por sha256, entrega sempre pela API

Opções: (a) arquivos no disco em `data/<inquilino>/` (o SIG de teste interno, LIDO em `_save()`); (b) Garage (S3)
com bucket por inquilino, chave de escrita da API e chave só-leitura por inquilino, cota por bucket pela API admin
(GARAGE-admin); (c) MinIO (arquivado, DOC.md 17.1).

Recomendação: (b), reusando o daemon `plataforma-garage` com buckets e chaves próprias (D26 do dono: subir
`plat-garage` separado custa a mesma coisa em disco e dobra a operação; mudar depois = copiar buckets). Motivos:
MEDIDO: Garage 2.3.0 ativo, 27 MB de RAM (DOC.md 17.1), range request 206; a spec 17.4 fixa "bucket + chave + cota
por cliente"; L1 (COG), L2-03 (anexos), L0-03-g (miniaturas), L0-06 (backups) e L0-04 (arquivos fonte) precisam do
mesmo lugar. Regras: chave de objeto `<classe>/<uuid>/<sha256>.<ext>` e nunca sobrescrever (o bug do cache VSI do
TiTiler já foi visto na casa, `pipeline/README.md`); o navegador nunca fala com o Garage: a API checa `pode_ler` e
serve (nginx `X-Accel-Redirect` para não passar bytes pelo Python, medido no item); URL pré-assinada só entre worker e
Garage; varredura de órfãos periódica; `plat.arquivo` com RLS guarda o índice.

Custo de mudar: médio (copiar buckets; o índice no banco não muda).

Obriga: L1-01/L1-02 usam a chave só-leitura por inquilino já criada aqui; L7-07 replica o Garage; L7-11 (appliance)
instala o mesmo binário.

## D14. Eventos e auditoria: `evento` append-only com vocabulário espelhado nos gatilhos de webhook da Esri + `historico` por gatilho

Opções: (a) só `log_acesso` (ADR); (b) `evento` de domínio escrito pela API por função SECURITY DEFINER +
`historico` antes/depois por trigger nas tabelas de catálogo; (c) event sourcing completo.

Recomendação: (b). Motivos: DOCUMENTO: o audit log da Esri cobre membro, papel, grupo, compartilhamento, dono e item
(E11-audit) e os webhooks da organização disparam por `/items/*`, `/groups/*`, `/users/*` e `/roles/*` (E11-wh-triggers,
lista literal no handoff); usar o mesmo vocabulário traduzido faz L7-08 (webhooks) ser só uma entrega HTTP sobre
`evento` e faz a paridade ser linha a linha. O `historico` por trigger é o padrão já testado do SIG de teste interno
(`fn_historico`, LIDO), sem `geom`. Retenção 12 meses (spec 17.4) com partição mensal criada pelo periódico.
Cobrimos também a leitura por token (log_acesso), que a Esri não registra (E12-portallogs).

Custo de mudar: baixo (vocabulário cresce por migração).

Obriga: toda rota de escrita de qualquer linha grava evento (teste enumera o OpenAPI); L7-06 exporta para SIEM;
L7-12 usa `evento` como registro de tratamento.

## D15. Backup em duas fases: dump lógico por inquilino agora; PITR com pgBackRest quando o Postgres puder reiniciar

Opções: (a) só `pg_dump` (o SIG de teste interno: diário, 14 cópias, restore drill em banco temporário, LIDO em
`backup.sh`/`restore_test.sh`); (b) pgBackRest com WAL contínuo (RPO ≤ 15 min da spec 17.4); (c) réplica em
streaming (L7-07).

Recomendação: (a) agora como L0-06-a, (b) como L0-06-b atrás da decisão D22. Motivos: MEDIDO: `archive_mode=off`;
ligar exige reiniciar um Postgres compartilhado por outros serviços em produção (guardrail: nunca tocar os serviços dos SIGs de teste interno,
geoapp e a esteira de imagens em produção) — não é decisão deste laço; `pgbackrest` e `rclone` ausentes. DOCUMENTO: a Esri faz backup full do
relational data store a cada 4 dias por padrão e PITR opcional com incrementais a cada 5 min (E12-ds-backups), e o
`webgisdr` não inclui caches de tile, dado referenciado nem spatiotemporal (E11-webgisdr-ov) — nossa paridade lista
isso. O dump por schema `d_<slug>` (D3) é o que dá restauração e exportação por inquilino; o manifesto de objetos do
bucket vai junto. O drill mensal e o curto no `make check` são obrigatórios (a spec promete "restore drill mensal
publicado").

Custo de mudar: baixo (as duas fases coexistem; (b) não substitui (a): o dump por inquilino continua sendo o escrow).

Obriga: L7-06 lê `plat.backup` e `plat.backup_drill`; L7-07 usa o repositório pgBackRest para a réplica; L7-11 embala
o dump como parte do pacote.

## D16. Cotas: por inquilino, medidas diariamente, aplicadas na entrada, sem crédito nem assento

Opções: (a) só `cota_bytes` (ADR) checado no upload; (b) `cota_bytes` + `cota_usuarios` + `cota_itens` +
`cota_jobs_dia`, medição diária em `plat.uso_inquilino` (banco por schema, bucket pela API admin, itens, usuários
ativos, jobs, requisições/bytes do `log_acesso`), reserva atômica na criação; (c) crédito por operação (Esri).

Recomendação: (b). Motivos: spec (17.3/21): "taxímetro de TB, sem crédito" é o argumento comercial; DOCUMENTO: o
Enterprise não tem cota por membro (a doc de armazenamento trata de onde o dado fica, `plan/user-storage`), o
GeoServer só limita cache de tiles (500 MiB padrão, GS-quota) — a cota por inquilino é diferencial e é o que L7-09
fatura. Reserva atômica (`SELECT ... FOR UPDATE` no tenant) evita a corrida de 20 uploads paralelos (refutação do
item). A lixeira conta na cota.

Custo de mudar: baixo.

Obriga: L1-01 (COG conta no bucket), L2-05/L3 (resultado conta como camada), L7-09 (medição = esta série).

## D17. Metadado: procedência da casa em todo item + Perfil MGB 2.0 (ISO 19115-1) em jsonb com um único armazenamento; XML ISO 19139 gerado; catálogo externo OGC API Records + CSW próprio

Opções: (a) só os campos básicos do item; (b) jsonb com JSON Schema do Perfil MGB 2.0 (INDE) e exportação/importação
XML ISO 19139/19115-3 por modelo; (c) GeoNetwork/pycsw como serviço.

Recomendação: (b), com o bloco de procedência (fonte, URL, licença, data do dado, data de acesso, gerador, sha256,
método, confiança, limites, frescor, próxima verificação) em TODO item de dado desde L0-09-a, porque é o que a casa
já mede (catálogo de camadas do motor logístico com 23 colunas e 298 camadas; `acervo.fonte` com 376 fontes e
`v_completude` de 10 campos, LIDOS) e porque "procedência errada é pior que nenhuma" (regra da casa). DOCUMENTO: a
Esri guarda sempre no "ArcGIS metadata format" e só muda o estilo de apresentação (E11-metadata); o título NÃO é
sincronizado lá (limitação literal) — aqui é. INDE: o Perfil MGB 2.0 é o perfil brasileiro do ISO 19115 e o catálogo
da INDE é GeoNetwork (harvest por CSW). RAM (3 GB) descarta (c) como serviço; pycsw/pygeoapi ficam como referência
de conformidade. Validação XML com lxml (presente) e XSD do ISO/TC 211 guardados no repositório (pequenos).

Custo de mudar: médio (o jsonb é o armazenamento; trocar o perfil é trocar o schema e a apresentação).

Obriga: L1-01 (STAC ↔ metadado: campos comuns mapeados), L6-01 (acervo preenche procedência), L2-08 (importa metadado
do item Esri), L7-12 (classificação e retenção no mesmo bloco).

## D18. Contrato de API: erros JSON fixos, paginação, sem versão na URL, limites em código e documento gerados do mesmo lugar

Recomendação: `{erro, mensagem, detalhe?, req_id}` com os códigos declarados (400/401/403/404/409/410/413/422/423/
429/503), paginação `limite/deslocamento` + `total`, datas ISO 8601 UTC, ids UUID, português nos identificadores
(ADR 12), sem `/v1` (mudança incompatível = rota nova; o OpenAPI comitado é o contrato e o `git diff` mostra a
mudança), CORS por lista do inquilino (≤ 100 origens como a Esri, E11-security), rate limit por sessão/token/IP,
`docs/LIMITES.md` gerado de `app/limites.py` e conferido por teste. A API Esri-compatível (`/svc/`) e OGC (`/ogc/`)
são contratos separados (L2-04) e não seguem este formato de erro (seguem o da Esri e o do OGC).

Custo de mudar: alto se decidido tarde (todo cliente e SDK dependem); por isso é o item L0-12, antes das rotas.

Obriga: todas as linhas.

## D19. Extensibilidade: registro de tipos de item, de tarefas de job, de privilégios, de eventos e de módulos do front, sempre por migração + registro em código

Recomendação: quatro registros (`tipo_item`, tarefas com decorador, `privilegio`, vocabulário de `evento`) e uma
convenção de front (módulo ES por tipo de item, ≤ 60 kB, sem bundler, ADR 11) são a superfície pela qual L1-L6
acrescentam capacidade sem tocar em L0. Regra: item de outra linha que precise de coluna nova em `item` ou `job`
está errado; usa `dados jsonb` validado pelo seu schema.

Custo de mudar: baixo.

## D20. Isolamento por inquilino: um portal, N inquilinos, RLS em tudo, superadmin fora de inquilino, teste cruzado automático

Recomendação: a Esri isola por portal (1 portal = 1 organização; várias = vários portais ou collaboration,
E12-access), o GeoServer por workspace isolado (GS-workspaces, "Isolated workspace") e regras por camada
(GS-layersec, modo hide/mixed/challenge), o QWC por `tenantConfig.json` e schema de configuração por inquilino
(QWC-multitenancy). Aqui: `tenant_id` + RLS em toda tabela (catálogo, dado, job, arquivo, evento), schema de dado por
inquilino, bucket por inquilino, funções SECURITY DEFINER com checagem interna de inquilino e sem EXECUTE para PUBLIC
(achado do adversário do T1), superadmin com console próprio (L0-07-f) e gerador de teste cruzado que enumera o
OpenAPI (L0-02-e) como portão P6 executável para todo item futuro. Modo "hide" do GeoServer é o nosso 404 para item
sem acesso.

Custo de mudar: não se muda; é o que o produto vende.

---

## Anexo A — URLs testadas (HTTP HEAD, 2026-09-05 12:39-13:03 UTC; código final e endereço efetivo = o próprio)

Série 11.4 (versão-alvo): E11-security configure-security.htm · E11-tokenexp specify-the-default-token-expiration-time.htm ·
E11-audit understand-audit-logs.htm · E11-members manage-members.htm · E11-roles roles.htm · E11-priv
privileges-for-roles-orgs.htm · E11-usertypes user-types-orgs.htm · E11-licenses manage-licenses.htm · E11-saml
configuring-a-saml-compliant-identity-provider-with-your-portal.htm · E11-oidc openid-connect-logins.htm · E11-newmember
configure-new-member-defaults.htm · E11-general configure-general.htm · E11-home configure-home.htm · E11-map
configure-map.htm · E11-gallery configure-gallery.htm · E11-groupscfg configure-groups.htm · E11-classif
configure-classification-schema.htm · E11-orgwebhooks configure-organization-webhooks.htm · E11-wh-triggers
webhook-triggers.htm · E11-wh-payloads webhook-payloads.htm · E11-usage about-usage-reports.htm · E11-manageitems
manage-items.htm · E11-webgisdr create-web-gis-backup.htm · E11-webgisdr-ov overview-backup-restore-web-gis.htm ·
E11-bkp-best backup-and-restore-best-practices.htm · E11-portalscan scan-your-portal-for-operational-health-issues.htm ·
E11-portallogs work-with-portal-logs.htm (todas em `https://enterprise.arcgis.com/en/portal/11.4/administer/windows/`);
E11-itemdetails item-details.htm · E11-configitem configure-item-details.htm · E11-share share-items.htm · E11-groups
create-groups.htm · E11-search search.htm · E11-metadata metadata.htm · E11-supported supported-items.htm · E11-hosted
hosted-web-layers.htm · E11-categories content-categories.htm · E11-delete delete-items.htm · E11-move move-items.htm ·
E11-addfiles add-files-as-items.htm · E11-publishfeat publish-features.htm · E11-csvgpx csv-gpx.htm · E11-managehfl
manage-hosted-feature-layers.htm · E11-dsitems data-store-items.htm (em `.../portal/11.4/use/`); E11-ds-what
`https://enterprise.arcgis.com/en/data-store/11.4/install/windows/what-is-arcgis-data-store.htm` · E11-ds-utils
`.../data-store/11.4/install/windows/data-store-utility-reference.htm`.

Série 12.1 (usada onde a 11.4 não tem página com o mesmo nome; o handoff 21_esri.md provou que "latest" = 12.1):
`https://doc.esri.com/en/arcgis-enterprise/12.1/administer/data-store-backups.html` (full a cada 4 dias; PITR com
incrementais a cada 5 min ou log cheio; 7 dias de incrementais) · `.../administer/data-store-recovery.html` ·
`.../administer/audit-logs.html` · `.../latest/share/create-hosted-views.html` · `.../latest/administer/migrate-group-content.html` ·
`.../latest/create/profile.html` · `.../latest/share/edit-metadata.html` · `.../latest/create/advanced-search.html` ·
`.../latest/share/limit-usage-of-secure-services.html` · `.../12.1/plan/user-storage.html` (sem cota por membro).

REST/Developers: generate-token, api-key-authentication, items-and-item-types, relationship-types, related-items,
recycle-bin-reference ("not supported in ArcGIS Enterprise"; Online ≥ 14 dias), status (jobType publish/export…),
add-item-part (partes 1-10.000, qualquer ordem), export-item (shapefile, csv, file geodatabase, feature collection,
geojson, geoPackage, kml, excel, vector tile package, mobile geodatabase), protect, reassign-item, search-reference,
create-folder, notifications, portal/indexer, portal/email-settings (smtpHost/Port/mailFrom; avisos 90/60/30/3/2/1 d),
portal/system-properties (privatePortalURL, WebContextURL, disableSignup), portal/license, gp-job (esriJob* e
progress a cada 5 s), server/jobs, portal/health-check-portal. Base de conhecimento: KB 000031852 (itens apagados) e
KB 000024210 (member must not own items).

GeoServer (docs.geoserver.org/stable/en/user/): security/index.html, security/layer/ (layers.properties, modo
hide/challenge/mixed), security/service/, security/usergrouprole/usergroupservices/ (XML, JDBC, LDAP), security/auth/index.html,
community/keycloak/index.html, data/webadmin/workspaces/ (isolated workspaces), extensions/importer/index.html,
extensions/importer/formats/, extensions/importer/rest_reference/, geowebcache/webadmin/diskquotas/ (500 MiB padrão,
desligado por padrão), community/backuprestore/index.html e usagerest/ (`/rest/br`, só configuração, não dado),
extensions/monitoring/audit/ (audit.enabled/path/roll_limit), extensions/metadata/, services/csw/, extensions/csw-iso/,
extensions/inspire/, configuration/status/, community/acl/, rest/index.html.

QGIS Server 3.40: server_manual/catalog.html (catálogo de projetos por `QGIS_SERVER_LANDING_PAGE_*`, inclusive projetos
em PostgreSQL), server_manual/config.html. QWC: docs.qwc.app/master/topics/MultiTenancy/.

PostgreSQL 16: ddl-rowsecurity, sql-select (SKIP LOCKED), sql-notify, textsearch-controls, textsearch-tables, unaccent,
pgtrgm, ltree, continuous-archiving, app-pgdump, pgcrypto. pgBackRest user-guide. Procrastinate: índice, retry,
cancellation, locks, cron, migrations. GDAL: drivers vector index, ogr2ogr, ogrinfo, shapefile, gpkg, csv, libkml, gpx,
xlsx, dxf, cad, dwg, openfilegdb, parquet, flatgeobuf, gml, pg. OGC API Records 20-004r1. INDE: Perfil MGB 2.0 (PDF)
e metadados.inde.gov.br/geonetwork/. OWASP Password Storage. RFC 6238. python3-saml, pysaml2, Authlib, Keycloak,
Microsoft Entra OIDC, ezdxf, ODA File Converter, Garage admin API e cookbook, LGPD (planalto), IBGE RPR 01/2015
(SIRGAS 2000), epsg.io/4674.

Não usadas como evidência (falharam no HEAD): `www.iso.org/standard/*` (403), `acesso.gov.br/roteiro-tecnico/*.html`
internos (500; a raiz responde 200), `www.gov.br/governodigital/...` (403), `ibge.gov.br/geociencias/...` (403),
pycsw `ogcapi-records.html` e pygeoapi `data-publishing/ogcapi-records.html` (404: só as raízes das docs foram citadas).

## Anexo B — o que a L0 dá de graça às outras linhas (para não reescreverem)

Modelo de item e tipos (D2), tabela de camada com RLS (D3), CRS (D4), privilégios (D5), compartilhamento e
`pode_ler` (D7), busca (D8), relações (D9), lixeira e versões (D10), inspeção/importação/exportação por job (D11), fila
(D12), objetos (D13), eventos (D14), backup por inquilino (D15), cotas (D16), procedência e metadado (D17), contrato de
API (D18), teste cruzado automático (D20), CLI (`plat`), dado de demonstração aberto (L0-13).

## Anexo C — o que fica fora da L0 e onde mora

Serviços Esri-compatíveis e OGC de feição (L2-04), tiles vetoriais e raster (L2-01, L1-02), estilo (L2-02), edição de
feições e anexos (L2-03), geocodificação de CSV com endereço (L2-11-a), webhooks HTTP (L7-08-a), antivírus de upload
(L7-03-a), observabilidade/alertas (L7-06), réplica e HA (L7-07), i18n das telas (L7-10), classificação/retenção LGPD
(L7-12), Notebook Server/scripts (L2-16), Data Pipelines (L5-02), colaboração distribuída entre portais (sem
equivalente; registrado como fora), licenças por membro/arquivo do My Esri (sem equivalente por decisão da spec).
