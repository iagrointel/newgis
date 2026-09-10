# ADR 20260907T1630 — Sistema de referência (CRS) como serviço transversal (L2-17-crs-transformacoes)

Estado: aceito (dados+cartógrafo+backend+frontend+adversário, turno T3, setembro de 2026). Base:
`laco/estado.json` item `L2-17-crs-transformacoes` (hipótese, portão de pronto, refutação). Nome de
arquivo em carimbo de tempo, não número sequencial: dois `0018` colidiram no mesmo minuto em 06/09
(adendo do brief comum das trilhas) — a mesma regra do nome de migração (ADR 0014) vale para ADR.

## 1. Contexto

Toda camada carregada nesta plataforma (item L0-04-c) guarda o SRID nativo do arquivo original — a
regra da casa é NUNCA reprojetar na ingestão. Isso empurra a responsabilidade de "em que CRS eu recebo
o dado" para os SERVIÇOS (OGC, catálogo, mapa, ferramentas de medição), e cada um deles reprojetando do
seu jeito diverge cedo ou tarde: o backend usando um EPSG, o navegador usando outro texto proj4 digitado
à mão, o SIG legado do Brasil (SAD69, Córrego Alegre) sem transformação de datum nenhuma porque "ninguém
lembrou da grade". Este item cria UM lugar só — `app/crs/` — de onde toda a plataforma lê o registro de
CRS e pede transformação, e nenhum outro módulo digita uma string proj4 ou um parâmetro de datum de
novo (o próximo consumidor natural é a ferramenta "reprojetar" do item L2-05-b, ainda não construído).

## 2. Decisão: sem tabela `plat.*` própria (mesmo padrão de `app/rede`, L2-11-c)

Não há linha de banco por inquilino aqui — o registro de CRS é o banco EPSG embutido no PROJ da máquina
(`pyproj` 3.7.2, PROJ 9.4.0), mais uma lista curada (`app/crs/curada.py`) e três grades NTv2 do IBGE
vendorizadas (`grades_ibge/`). RLS (P6) não se aplica pelo mesmo motivo do geocodificador (ADR 0013 §2)
e da rede de rota: dado aberto, igual para todo inquilino. A API exige autenticação (sessão ou token com
o escopo novo `crs:usar`, `app/auth/escopos.py`), sem filtro de `tenant_id`.

## 3. Por que grade `.gsb` vendorizada em vez do CDN do PROJ (`cdn.proj.org`)

PROJ 9.4 sabe buscar a grade oficial do IBGE sozinho — a operação EPSG "SAD69 to SIRGAS 2000 (2)"
referencia `br_ibge_SAD69_003.tif` em `https://cdn.proj.org/...` (medido: `TransformerGroup(4618, 4674)`
lista essa operação como `unavailable`, com a URL, até a rede ser ligada). Não usamos isso em produção:
ADR 0001 seção 11.4 já proíbe CDN de terceiro nas dependências do frontend, e o mesmo princípio vale aqui
— um serviço de reprojeção que depende de rede externa quebra silenciosamente atrás de firewall/proxy, e
o PostGIS deste ambiente já roda com `NETWORK_ENABLED=OFF` (medido: `PostGIS_Full_Version()`). Solução:
os `.gsb` originais do IBGE (mesmo conteúdo, formato NTv2 clássico, dado aberto) ficam commitados em
`grades_ibge/` — mesmo padrão de `osrm/*.osrm` (dado derivado versionado, não CDN, não pipeline externo
em produção) — e são lidos por CAMINHO ABSOLUTO num pipeline PROJ sem CRS nas pontas:

    +proj=pipeline +step +proj=hgridshift +grids=<caminho absoluto do .gsb>

Isso funciona idêntico em `pyproj.Transformer.from_pipeline` (backend) e em `ST_Transform(geom, texto)`
(PostGIS — mesma libproj) sem precisar copiar nada para `/usr/share/proj` (fora de
`/home/dev/plataforma/`, proibido pela regra 1 do brief) nem definir `PROJ_DATA`/`PROJ_LIB` compartilhado
entre processos.

## 4. Como se prova que o pipeline está montado certo (não só "compila sem erro")

Ter o `.gsb` certo não prova que o pipeline (sem CRS declarado, ordem de eixo implícita) está montado
sem inverter sinal/eixo. A prova usada foi um serviço vivo e independente: `servicodados.ibge.gov.br/
api/v1/progrid` (API oficial do IBGE, descoberta por busca — não documentada nos materiais estáticos
achados antes), que devolve `"tipo_conversao":"grid"` quando usa a mesma malha. Para 10 coordenadas
SAD69 dentro da cobertura, o pipeline local bateu com a resposta oficial a ≤ 0,07 mm — bem abaixo dos
50 mm exigidos pelo portão (`tests/unit/test_crs_grade_ibge.py`, fixture
`tests/dados/pontos_ibge_sad69_sirgas2000.json`, proveniência completa em `grades_ibge/PROVENIENCIA.md`).
Um exercício universitário independente (UFPR, prof. Carlos Aurélio Nadal) aplicando os parâmetros de
7/3 do R.PR IBGE 01/2005 à estação RBMC de Chapecó bateu com os mesmos parâmetros usados aqui como
alternativa sem grade — segunda fonte independente, mesmo resultado.

## 5. Escolha de transformação por área (o "datumTransformation" do Esri, sem o Esri)

`app/crs/grades.py::transformar_datum_legado` escolhe a grade certa pelo `bounds` de cada uma (lido do
registro EPSG via `pyproj.transformer.TransformerGroup`, não digitado): SAD69 nacional, Córrego Alegre
1961 (18°S-27°30'S) e Córrego Alegre 1970/72 (o resto do país). Fora de qualquer grade, cai na
alternativa SEM grade — parâmetros geocêntricos do R.PR IBGE 01/2005, classe de exatidão EPSG 5,0 m —
e a resposta DECLARA qual das duas foi usada (`transformacao_usada`, `cobertura`). Isto é o pedido da
refutação do item: "transformação SAD69 fora da cobertura da grade deve declarar a transformação
alternativa usada", não falhar nem devolver um número plausível e escondido.

## 6. Eixos trocados: detecção por área de uso, não só por `|lat|>90`

A checagem óbvia (`|lat| > 90` não é latitude válida) não pega a maioria dos casos reais no Brasil:
longitude e latitude brasileiras cabem as duas em `[-90, 90]`, então um par trocado passa incólume nessa
checagem. `app/crs/servico.py::_checar_eixos_geograficos` usa a SEGUNDA checagem: se o ponto como veio
cai FORA da área de uso do CRS de origem mas o ponto TROCADO cai DENTRO, é forte indício de inversão —
testado com um ponto real (São Paulo) trocado, que a primeira checagem não pegaria.

## 7. O que fica de fora (paridade com "coordinate systems and transformations" do Esri)

O Map Viewer do ArcGIS Online também não desenha o mapa em qualquer projeção — ele exige um mapa-base
compatível para trocar de CRS de exibição. Esta plataforma tem a MESMA limitação, e pelo mesmo motivo
técnico: o MapLibre GL (a biblioteca de mapa desta casa, ADR de `L2-01-a`) desenha SEMPRE em Web Mercator
(EPSG:3857) — não existe modo "desenhar o mapa em UTM ou Policônica" no MapLibre como existe em produtos
Esri com múltiplos "spatial reference" de exibição. A ferramenta `/crs` deste item converte coordenada e
bbox por qualquer CRS curado (é o que os relatórios/exportações/medição precisam), mas o MAPA em si
segue só em 3857 — documentado aqui, não escondido, porque um usuário vindo do ArcGIS pode esperar
"mudar a projeção do mapa" e isso não existe nesta pilha ainda.

## 8. Consumidores futuros

A ferramenta "reprojetar" do item L2-05-b (ainda não construído) deve chamar `app.crs.servico` em vez de
reimplementar; o navegador usa `proj4js` (vendorizado, `web/vendor/proj4-2.15.0.js`) só para exibição e
entrada de coordenada — nunca para o datum legado (isso fica no backend, que tem a grade) — com as
definições vindas de `/api/crs/{epsg}.proj4`, para nunca haver uma segunda cópia da definição do CRS
divergindo da primeira.
