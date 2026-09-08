# ADR 0013 — Geocodificador próprio em PostgreSQL (L2-11-b-geocodificador-brasil)

Estado: aceito (pesquisador+dados+backend+adversário, turno T3, setembro de 2026). Base: `laco/estado.json`
item `L2-11-b-geocodificador-brasil` (hipótese, portão de pronto, refutação); D28 (teto de disco do laço,
≤ 3 GB de trabalho por turno). Sem Nominatim/Pelias instalados (exigem o OSM completo do Brasil em disco,
gigabytes que a máquina não tem — a decisão do dono foi construir um geocodificador PRÓPRIO sobre o mesmo
banco Postgres/PostGIS que já roda a plataforma).

## 1. Contexto

O ArcGIS Enterprise publica um `GeocodeServer` (locator) a partir de uma tabela de referência de
endereços — no Brasil, tipicamente construída sobre o Cadastro Nacional de Endereços para Fins
Estatísticos (CNEFE) do IBGE, base do Censo 2022, porque é o único cadastro de endereço nacional aberto
com coordenada por face de quadra (o cadastro dos Correios não é aberto). A casa já usa CNEFE em três
frentes (`<frente_a>.geo_cnefe_*`, `<frente_b>.cnefe*`, `<frente_c>.cnefe`), sempre como camada de apoio (agregado por
CEP/bairro, ou já casado com outra fonte) — nenhuma delas é um GEOCODIFICADOR (busca por endereço →
coordenada, hierarquia de recuo, reverso, sugestão, protocolo Esri). Este item constrói isso do zero,
schema `plat`, sem tabela de nenhuma outra frente tocada.

## 2. Decisão: schema global (sem `tenant_id`), mesmo padrão de `plat.rota`/`plat.acervo_ficha`

`plat.geo_uf`, `plat.geo_municipio`, `plat.geo_endereco`, `plat.geo_instalacao` não têm `tenant_id`: é
referência ABERTA do IBGE, igual para todo inquilino, no mesmo papel de `plat.acervo_ficha` (migração 021)
e da rede de rota do item L2-11-c (que nem tabela tem, roda sobre um OSRM de teste). P6 (RLS obrigatório)
não se aplica — não há linha de banco pertencente a um inquilino aqui. A API exige autenticação (sessão ou
token com escopo `geocodificar:usar`, novo em `app/auth/escopos.py`), mas não filtra por `tenant_id`.

## 3. Fonte, esquema e o que a carga corrige

Fonte: `https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/
Arquivos_CNEFE/CSV/UF/<cod>_<sigla>.zip` (medido por `HEAD` antes de baixar — `scripts/geocodificador_
instalar_uf.py`); nome de município vem da API pública do IBGE (`servicodados.ibge.gov.br/api/v1/
localidades/estados/<cod>/municipios`), porque o CNEFE não traz nome de município, só o código.

Achado na carga (06/09/2026, Roraima): `COD_UNICO_ENDERECO` **não é chave única** — 260.516 linhas do
arquivo, só 249.268 valores distintos (o IBGE repete o código quando há mais de um domicílio/estabelecimento
na mesma coordenada). `plat.geo_endereco` usa `id bigserial` como chave primária de verdade e guarda o
código do IBGE em `cod_unico_endereco` (indexado, não único) — o esquema inicial (chave = `COD_UNICO_
ENDERECO`) foi escrito, testado, reprovado por uma violação de unicidade real na primeira carga, e corrigido
ANTES de qualquer commit (a migração aplicada errada foi apagada do banco e reescrita; nada disso ficou
em `db/migracoes/045_geocodificador.sql`, que já nasce com o esquema certo).

Normalização em duas camadas (nunca uma reimplementação da outra):
1. **Acento/caixa**: sempre `upper(public.unaccent(...))` em SQL — carga (`UPDATE` logo após o `COPY`) e
   consulta (`WHERE coluna % upper(unaccent(%s))`) usam a MESMA função do Postgres, então nunca divergem.
   O CNEFE em si já vem ASCII puro (conferido byte a byte na amostra de Roraima — sem acento a remover),
   então esta camada importa principalmente para o texto que o USUÁRIO digita.
2. **Abreviação/ordinal**: só em Python (`app/geocodificador/normalizacao.py`), porque não existe função de
   banco para isso — dicionário fechado de tipo de logradouro (R. → RUA, AV. → AVENIDA, ...) e ordinal
   (1º/1ª → 1), aplicado tanto na carga (ao concatenar tipo+título+nome) quanto na consulta.

## 4. Hierarquia de recuo e o "tipo de acerto"

`app/geocodificador/motor.py::buscar()`, do mais preciso ao menos preciso, sempre marcado em
`tipo_acerto` na resposta: `numero_exato` (ponto do CNEFE com o mesmo número) → `interpolado_na_face`
(número entre dois pontos conhecidos da MESMA face — `cod_setor/num_quadra/num_face` — interpolado
linearmente; a face com a faixa mais estreita que cobre o número pedido vence, para não interpolar sobre
uma quadra inteira quando uma face mais específica está disponível) → `aproximado_no_logradouro` (nenhuma
face cobre o número; ponto mais próximo por número na mesma via) → `aproximado_no_bairro` (via não
encontrada; centróide do `DSC_LOCALIDADE` do IBGE, usado como bairro) → `aproximado_no_cep` → `aproximado_
no_municipio`. Pontuação (`score`, 0-100): similaridade trigram do logradouro × 100, com penalidade por
degrau de recuo (0 no número exato, até 50 no centróide do município) — mesma ideia do `score` do
`findAddressCandidates` da Esri, sem replicar a fórmula exata dela (não publicada).

**Interpolação por face é mais fiel que a interpolação clássica por trecho de rua** (a técnica usual de
geocodificador, que assume distribuição linear de números num INTERVALO declarado do logradouro): aqui os
pontos-âncora são coordenadas REAIS do censo, não extremos de um trecho — quando a face tem 2+ pontos
medidos, a interpolação corre entre medições de verdade, não entre suposições.

## 5. Consistência CEP × município × UF (a refutação do item-pai)

`motor.resolver_lugar()` roda ANTES de qualquer busca por logradouro: se o chamador informa CEP e
município (ou CEP e UF) que não correspondem ao mesmo lugar no CNEFE carregado, a API RECUSA com `422`
(`cep_municipio_inconsistente` / `cep_uf_inconsistente`, com o lugar correto do CEP no detalhe) — nunca
devolve um candidato de um lugar não pedido. Um município desconhecido (erro de digitação, ou fora da UF
instalada) não é tratado como inconsistência: a busca por logradouro simplesmente AMPLIA o escopo (procura
sem filtro de município), o mesmo comportamento que resolve a ambiguidade de "Rua A" — ver seção 8.

## 6. API própria e GeocodeServer compatível

`POST /api/geocodificar` (linha única `endereco` OU campos estruturados, os dois podem se misturar — o
que faltar num é completado pelo outro), `POST /api/reverso` (KNN por `<->` sobre índice GiST em
`geom geometry(Point,4326)`), `GET /api/sugerir` (prefixo sobre o índice GIN trigram, medido: p95 33 ms
com 260 mil linhas). Mesmo motor por trás de `/rest/services/Geocodificador/GeocodeServer/{findAddress
Candidates,reverseGeocode,suggest,geocodeAddresses}` — protocolo real do ArcGIS Enterprise (fontes datadas
06/09/2026 em `developers.arcgis.com/rest/services-reference/enterprise/...`), autenticado por
`?token=<token de serviço plat>` (querystring, como o Esri realmente manda) além do `Authorization: Bearer`
normal — reaproveita `app.auth.sessao._auth_de_token` (função "privada" do módulo, mesmo pacote `app`; ver
docstring de `app/geocodificador/rotas_esri.py`) para não duplicar a validação de token. Tabela de
paridade (feito/parcial/fora) em `docs/PARIDADE.md`.

## 7. Instalação por UF

`scripts/geocodificador_instalar_uf.py --uf <SIGLA>`: mede o tamanho por `HEAD` antes de baixar (teto
padrão 200 MB comprimidos, D28; `--forcar` ignora), baixa em streaming com sha256 acumulado, lê o zip
membro a membro (nunca extrai por inteiro em disco) e carrega por `COPY` em lotes de 20 mil linhas — baixo
consumo de memória e de tempo. Reinstalar a mesma UF apaga e recarrega (idempotente, nunca duplica).
Proveniência gravada em `plat.geo_instalacao` (tamanho do zip, do CSV, linhas, municípios, duração, sha256
do zip) — é dali que qualquer documento cita o número, nunca de memória.

**Demo escolhida por tamanho de arquivo, não por familiaridade**: Roraima (14_RR.zip, 4,52 MB comprimidos,
42,05 MB de CSV) é o MENOR entre os 27 arquivos de UF do IBGE (medido por `HEAD` em todas as 27 UFs antes
de escolher: Amapá 5,45 MB, Acre 7,02 MB, Sergipe/DF na casa de 20 MB, os demais maiores) — carga completa
em 10,4 s, 260.515 linhas, 15 municípios, tabela final com índices em 126 MB.

## 8. Sem São Paulo: como a refutação de ambiguidade foi provada mesmo assim

O adversário do item-pai pede especificamente "buscar 'Rua A' em São Paulo (ambiguidade — múltiplos
resultados esperados, não erro)". São Paulo é o MAIOR arquivo de UF do CNEFE (não medido aqui por decisão
de escopo — o item nunca pretendeu instalar SP, só demonstrar o mecanismo com uma UF pequena) — carregá-lo
só para este teste violaria D28. Roraima tem o MESMO fenômeno em escala menor, medido: `RUA A` se repete em
**8 dos 15 municípios** de RR (junto com `RUA B`, `VICINAL SEIS`/`VICINAL TRES` em 10 municípios cada — nomes
genéricos de loteamento/vicinal se repetem entre municípios em qualquer UF). Os testes usam essa ambiguidade
real de RR, documentada explicitamente como substituta de SP (nunca disfarçada de "São Paulo testado").

## 9. O que ficou de fora (pendências nomeadas, nunca "feito")

- **QGIS como localizador real, com captura de tela**: esta máquina não tem QGIS instalado nem ambiente
  gráfico (X/Wayland) — mesma classe de limitação do Chrome headless já registrada em `CLAUDE.md`
  (`google-chrome headless quebra nesta máquina`). O protocolo foi testado por chamada HTTP direta
  simulando exatamente o que o QGIS manda (`findAddressCandidates`/`suggest`/`reverseGeocode` com
  `SingleLine`/`text`/`location` e `token=` na querystring — ver `tests/api/geocodificador/
  test_geocodificador_esri.py`), o que prova o protocolo, não a integração do produto QGIS em si.
  **Pendência real, registrada aqui e em `docs/PARIDADE.md`, nunca marcada como feito.**
- **ArcGIS Pro / AGOL reais**: pendente de credencial do parceiro (decisão D20, já aberta para toda a
  plataforma).
- **Item L2-11-a-geocodificacao-csv** (geocodificação em lote de planilha/CSV do usuário): item-irmão
  ainda não construído; reusa `motor.buscar()` e o caminho `geocodeAddresses`, sem trabalho novo de banco.
- **Segunda UF para consistência cruzada de CEP entre estados diferentes**: o teste de inconsistência
  (seção 5) foi provado DENTRO de Roraima (CEP de um município pedido com o nome de outro município da
  mesma UF) — mais barato em disco/RAM que carregar uma segunda UF só para esse teste, e prova a mesma
  lógica (`resolver_lugar()` não sabe se o conflito é intra ou inter-UF, o código é o mesmo).
