# ADR 0020 — Conector ArcGIS REST externo (item L6-02-d-arcgis-rest-externo)

Estado: aceito (arquiteto+backend+esri+adversário desta sessão, turno 5, 07/09/2026). Base: modelo de
conexão e defesa de SSRF do item L6-02-a (ADR 0012, `app/conexao/seguranca.py`) e o padrão já fechado pelo
conector WMS/WMTS (item L6-02-b): um módulo "motor" sem I/O de rede fora de `buscar_seguro`, um módulo de
rotas `rotas_esri_rest.py` pendurado em `/api/conexoes/{id}/esri/*`, testes de unidade sem rede + testes de
API com rede real contra serviço público brasileiro.

## Contexto

A hipótese do item cobre três recursos de um Portal/AGOL de terceiro: FeatureServer (query paginado),
MapServer (imagem dinâmica) e ImageServer (raster referenciado), nos modos referenciado e copiado. Esta
trilha entrega o modo REFERENCIADO inteiro; o modo copiado (materializar em PostGIS) fica de fora, nomeado
como fronteira honesta — reproduz a mesma decisão que o L6-02-b tomou para a cláusula EPSG:4674 exata (o
que não coube no turno não aparece como "feito").

## Decisão 1 — a conexão guarda a URL RAIZ do serviço, não a de uma camada

`plat.conexao.url` para `tipo=esri_rest` é sempre `.../FeatureServer`, `.../MapServer` ou `.../ImageServer`
(sem sub-camada). Alternativa descartada: gravar a URL de uma camada específica (`.../FeatureServer/0`) —
funcionaria para o primeiro caso de uso mas obrigaria uma conexão por camada, quando um único FeatureServer
real (ex.: SIGEL/ANEEL `PORTAL/Camadas_Downloads`) declara 30+ camadas. O mesmo padrão já valia para o WMS
(uma `capabilities`, N `camada=` por operação) — reaproveitado aqui: uma conexão, N camadas por índice
numérico (`{camada}` na rota).

## Decisão 2 — tipo de serviço detectado da URL, nunca do corpo da resposta

`_tipo_servico()` lê o último segmento do path (`FeatureServer`/`MapServer`/`ImageServer`, case-insensitive)
por regex. Alternativa descartada: inferir do JSON de `?f=json` (presença de `layers` vs. `bandCount` etc.)
— funciona, mas exige uma chamada de rede só para decidir QUAL operação é válida (query vs. export vs.
exportImage), e a resposta de erro (`{"error":...}`) não permite a inferência. A URL já é a fonte de
verdade: o cliente escolheu que tipo de serviço registrar ao colar a URL.

## Decisão 3 — token como parâmetro de querystring, não cabeçalho Bearer

O teste de saúde genérico (L6-02-a) e o `wms_wmts` (L6-02-b) injetam a credencial como
`Authorization: Bearer <token>`. O ArcGIS Server clássico (token gerado por `generateToken`, ou o token de
item do AGOL) é validado como parâmetro `token=` na URL — testado contra o SIGEL/ANEEL real
(`SIGEL/Linhas_de_Transmissao` devolve `{"error":{"code":499,"message":"Token Required"}}`, nunca 401 com
`WWW-Authenticate`). `_token_da_conexao` decifra a mesma coluna `credencial_cifrada`; a rota anexa o valor
só na URL final da chamada ao serviço externo, nunca no cabeçalho — e nunca no corpo de resposta desta API.

## Decisão 4 — paginação com três travas independentes contra servidor hostil

A refutação do item ("adversário aponta serviço com `maxRecordCount = 1`") exige que o motor nunca trave.
`consultar_tudo` usa `tamanho_pagina = min(maxRecordCount do servidor, ESRI_REST_MAX_RECORD_COUNT_PADRAO)`
e três tetos independentes, na mesma linha do que o conector WFS (L6-02-c, ainda não integrado a master)
já fez para o mesmo problema: `ESRI_REST_PAGINAS_MAX` (teto absoluto de iterações, o que fecha o caso
`maxRecordCount=1` sozinho), `ESRI_REST_FEICOES_MAX` (teto de memória do modo referenciado) e o aviso
quando uma página devolve MAIS feições do que as pedidas (servidor ignora `resultRecordCount`). Provado
sem rede em `tests/unit/test_esri_rest_analise.py::test_consultar_tudo_para_no_teto_de_paginas_com_maxrecordcount_1`
(monkeypatch — não existe serviço público brasileiro conhecido com `maxRecordCount=1` para testar com rede
real, e simular isso contra loopback exigiria a válvula `PLAT_TESTE_CONEXAO_ALVOS` que só existe no ramo do
L6-02-c, não integrado a esta base).

## Decisão 5 — simbologia só do renderer `simple`

`simbologia_simples` só interpreta `renderer.type == "simple"` com símbolo `esriSFS` (polígono) ou
`esriSLS` (linha); `classBreaks`/`uniqueValue` (paleta por atributo) e `esriPMS`/`esriSMS` (marcador de
imagem/pontual, sem noção de "preenchimento") voltam `None`. A hipótese do item diz "simbologia simples
importada" — não "motor de renderização completo do ArcGIS"; inventar uma cor para um marcador de imagem
seria pior do que não desenhar nada (mesma regra da casa: procedência errada é pior que nenhuma).

## O que ficou de fora (nomeado, não escondido)

- Modo copiado (materializar FeatureServer em tabela PostGIS do inquilino, com agendamento) — item-pai
  `L6-02-conectores-vivos` continua em aberto para isso, mesmo padrão do L6-02-b/c.
- ImageServer `exportImage`: código e teste de unidade escritos; nenhum ImageServer público brasileiro foi
  encontrado nesta sessão (pesquisa registrada no handoff) para provar com rede real — mesma fronteira
  honesta que o L6-02-b nomeou para o WMTS em EPSG:4674 exato.
- PBF (`f=pbf`) como formato de saída da query paginada: a hipótese cita `f=geojson ou pbf`; só geojson foi
  implementado neste turno (é o formato que o resto da plataforma já consome — `app/conexao/proveniencia.py`
  e o item L2-04-c usam PBF só na direção OPOSTA, servindo dado nosso para cliente Esri, não lendo de
  terceiro). Registrado como pendência do item, não como decisão definitiva.
