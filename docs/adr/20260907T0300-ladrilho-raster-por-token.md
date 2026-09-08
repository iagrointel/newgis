# ADR 20260907T0300 — serviço de ladrilho raster com o token no caminho

Item: `L1-02-tiles-token`. Situação: aceito, com dois desvios do conceito L1 declarados abaixo.
Depende de: L1-01-a (pgstac + `plat.raster_item`), L1-01-ingest-raster (COG no Garage), L0-02-d (token
de serviço com escopo, restrição e revogação), L0-11 (armazenamento de objetos).

## 1. O contrato de URL é o produto, não um detalhe

O endereço do ladrilho é colado no web map de um cliente e fica lá por anos. Por isso ele é fixado
aqui e não muda: `/svc/<token>/raster/<item>/{z}/{x}/{y}[.png|.jpg|.webp]`, mais
`/tilejson.json`, `/info.json`, `/wmts` (KVP) e `/wmts/1.0.0/WMTSCapabilities.xml` (REST), e
`/svc/<token>/mosaico/<colecao>/{z}/{x}/{y}` para o mosaico da coleção.

O token vai no CAMINHO, não em parâmetro de consulta e não como URL assinada que expira (decisão C6 do
conceito L1, aqui só implementada): a documentação da Esri diz que serviço OGC protegido por
autenticação por token não é aceito no AGOL/Portal, e o que funciona é a URL com o segredo embutido.
URL que expira quebra o mapa salvo do cliente no dia seguinte.

Consequência aceita: quem tem a URL tem o dado. O que limita o estrago é o escopo em lista, a restrição
por Referer/CIDR, a revogação com efeito em segundos e o registro por token — todos já existentes no
`plat.token_servico`, nada novo foi inventado para tiles.

## 2. Recusa é 403, não 401

Todas as recusas do serviço de ladrilho (token inválido, revogado, expirado, escopo insuficiente,
Referer ou IP fora da restrição, item ou coleção de outro inquilino, item inexistente) respondem
**403**. Motivo: o token está no caminho — não há credencial a renegociar, e um 401 faria o navegador
abrir caixa de senha por um recurso que nunca a aceitaria. Item inexistente também dá 403, e não 404,
porque 404 confirmaria a existência do item para quem não pode vê-lo.

Isto difere do `/svc/<token>/stac/*` do L1-01-a, que responde 401. A diferença é deliberada e está
documentada aqui; unificar as duas é decisão do dono (não foi feita neste item para não mexer em
comportamento já entregue e testado).

## 3. Motor: rio-tiler dentro da aplicação, não uma unidade TiTiler separada

**Desvio declarado do conceito C5**, que recomendava a unidade `plat-titiler` (:8152) com
`titiler.core` e `path_dependency`.

O que se manteve: o motor é rio-tiler 9.4.3 — exatamente a biblioteca que roda dentro do TiTiler. Não
se escreveu motor raster próprio, que é o que a decisão C5 queria evitar.

O que mudou e por quê: as fábricas de rota do `titiler.core` publicam OUTRO contrato de URL
(`/tiles/{tileMatrixSetId}/{z}/{x}/{y}` com `?url=`), e o contrato desta casa é o da seção 1, que é
cláusula literal do portão do item. Montar as fábricas e depois reescrever caminho, parâmetro e
documento WMTS por cima dá mais código do que chamar `rio_tiler.io.Reader` diretamente — e deixaria
viva a rota com `?url=`, que é justamente o vetor de SSRF que a refutação do item manda atacar. Aqui
não existe nenhum parâmetro de endereço: o caminho do COG nasce da consulta ao catálogo do inquilino
do token (`plat.raster_item` com RLS, depois o item no pgstac, depois o asset). O teste
`test_nao_existe_parametro_de_endereco_de_arquivo` percorre o OpenAPI e reprova se algum dia aparecer.

Custo de voltar atrás: baixo. O contrato de URL esconde o servidor; trocar o interior por uma unidade
TiTiler mantém os endereços.

As rotas são síncronas (`def`, não `async def`): o FastAPI as executa no pool de threads, e a leitura
do GDAL, que é bloqueante, não trava o laço de eventos.

## 4. Leitura do COG: `/vsis3` com a chave só-leitura do balde do inquilino

O ladrilho é lido por faixa de bytes direto no Garage (`/vsis3/<balde>/<objeto>`), sem baixar o
arquivo. A credencial usada é SEMPRE a chave só-leitura do balde (`plat.arquivo_bucket.chave_ro_*`,
criada pelo L0-11) e vive só dentro do `rasterio.Env` da leitura; nada disso chega ao cliente.

Armadilha paga: o rasterio RECUSA opções `AWS_*` dentro de `Env` ("AWS config options can not be
directly set"); credencial vai por `rasterio.session.AWSSession`. As duas opções que não são
credencial e valem para a instalação inteira (`AWS_HTTPS`, `AWS_VIRTUAL_HOSTING`, porque o Garage local
fala HTTP com endereço no caminho) ficam no ambiente do processo, não por requisição.

## 5. Cache no nginx: chave sem o token, autorização por `auth_request`

A chave de cache é `<tipo>|<item>|<resto do caminho>|<query>` — **sem o token**, para que dois tokens
do mesmo inquilino compartilhem o ladrilho no disco. Isso obriga a duas coisas:

1. `auth_request` a cada requisição, contra `/api/tiles/autorizar`, ANTES de o nginx responder do
   cache; e
2. essa subrequisição confere **também o dono do item**, não só o token. Sem isso um token válido de
   OUTRO inquilino recebe o ladrilho alheio direto do cache, sem a aplicação ser consultada. Isso
   aconteceu na bancada de 07/09/2026, foi medido (200 onde devia ser 403) e é hoje um teste.

A resposta da autorização é cacheada 2 s no nginx; o mesmo dado é cacheado 2 s na aplicação. O pior
caso entre revogar um token e receber 403 é a soma, 4 s, abaixo dos 5 s do portão. **Medido: 2,86 s a
2,90 s em três repetições.**

Detalhe que custou 160× de desempenho: a aplicação põe `no-store` em TODA resposta (piso do middleware,
ADR 0002). Sem `proxy_ignore_headers Cache-Control` no bloco da autorização, o nginx não guarda a
subrequisição e cada ladrilho volta a bater na aplicação — medido 425 ladrilhos/s com ela indo à
aplicação, contra 68.738/s com ela em cache.

## 6. Expressão: gramática própria antes do numexpr

A expressão (`(b4-b3)/(b4+b3)` para NDVI) é a do rio-tiler, avaliada por numexpr, mas passa antes por
uma gramática desta casa (`app/imagens/tiles.expressao_valida`): só referência de banda `b1..b99`,
número, `+ - * / ( ) ,`, comparação e uma lista fechada de funções. Recusa por gramática, não por lista
negra — o que a gramática não reconhece, não passa. Sem referência de banda também não passa.

## 7. Grade e formatos

Só `WebMercatorQuad` (decisão C4). Formatos de ladrilho: PNG, JPEG e WEBP. Sem banda escolhida e com
raster de mais de 3 bandas, servem-se as 3 primeiras (regra escrita do perfil visual, C3); com
expressão, o asset padrão passa a ser o `cientifico`, porque a expressão precisa das bandas originais.

## 8. Mosaico

`/svc/<token>/mosaico/<colecao>/{z}/{x}/{y}` faz busca no pgstac pelas cenas que tocam o ladrilho,
ordenadas por data decrescente, e serve a primeira que responder. É o mínimo honesto: **não** é a busca
registrada do titiler-pgstac (C9), não há `pixel_selection` por pixel nem linha de costura. Está
declarado no docstring da rota e no handoff como o que falta para fechar o L1-07/L1-08.

## 9. Registro de uso

`plat.tile_leitura` (inquilino, token, item, dia) com contagem de ladrilhos, bytes e erros, escrita em
lote a cada 2 s por `app/imagens/leitura.py`. Uma linha por ladrilho em `plat.log_acesso` transformaria
a tabela de auditoria em fila de escrita. Perda aceita e declarada: até 2 s de eventos se o processo
morrer. O token nunca é gravado — só o `token_id`, como em `plat.log_acesso`.
