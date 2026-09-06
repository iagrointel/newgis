# ADR 0018 — Conector de feição externa: WFS 2.0 e OGC API - Features

Estado: aceito · Item `L6-02-c-wfs-ogcapi` (linha L6, conectores) · 06/09/2026
Depende de: ADR 0012 (registro do acervo e conexão externa, item L6-02-a) · ADR 0005 (ingestão vetorial).

## Contexto

`plat.conexao` (ADR 0012) já guarda a conexão a um serviço de terceiro, com defesa contra requisição forjada
pelo servidor (SSRF) e teste de saúde. Faltava o primeiro conector que de fato LÊ dado de um serviço: WFS 2.0
e OGC API - Features, os dois protocolos de feição que os órgãos brasileiros publicam (o GeoServer do IBGE, o
do ANP, os estaduais). O item pede os dois modos — referenciado (consulta ao vivo, com cache curto) e copiado
(traz para o PostGIS) — e o equivalente ao WFS em cascata do GeoServer.

## Decisões

### 1. Quem fala com o serviço externo é código nosso, nunca o driver do GDAL

O GDAL tem drivers `WFS` e `OAPIF` (presentes nesta máquina, GDAL 3.8.4, medido). Usá-los com a URL externa —
`ogr2ogr ... WFS:https://...` — seria menos código, e foi recusado: o driver faz a requisição HTTP por dentro
do `libcurl`, fora de `app.conexao.seguranca`, e a validação de esquema, de IP, de userinfo e de cada
redirecionamento deixaria de valer justamente no caminho que mais recebe URL de terceiro. Um endereço que
resolve para 169.254.169.254 passaria.

O desenho é: `app/conexao/vetor_externo.py` baixa cada página com `seguranca.buscar_seguro`, grava em arquivo
LOCAL no diretório do job, e só então o `ogr2ogr` entra, lendo arquivo local. Para que isso não dependa de
disciplina, o subprocesso roda com `GDAL_HTTP_PROXY=127.0.0.1:1` (porta fechada): qualquer requisição que o
GDAL tentasse fazer falha na hora, em vez de sair da máquina.

Custo aceito: a paginação, o `numberMatched` e a leitura do GetCapabilities/DescribeFeatureType são código
nosso, não do driver. Ganho: uma única porta de saída auditada, e controle exato sobre onde a cópia para.

### 2. O limite da cópia é da plataforma, não do serviço

`limite_feicoes` (padrão `CONEXAO_VETOR_LIMITE_PADRAO` = 100 mil) é o teto que a cópia aceita. Três travas
independentes encerram a paginação, e qualquer uma basta: o limite; a página maior do que a pedida (serviço
que ignora `COUNT`/`limit`); e a página que repete a primeira feição da anterior (serviço que não anda).
Somam-se o teto de bytes por página e o de páginas. O job então TERMINA — não falha, não trava —, marca
`limite_atingido` e escreve o aviso na procedência da camada, para quem abrir a camada daqui a um mês saber
que ela é um pedaço e não a coleção inteira.

### 3. CRS nativo declarado, geometria gravada em 4326

Reprojeção é nossa, com `ogr2ogr -s_srs/-t_srs`, nunca pedida ao serviço: `SRSNAME=urn:ogc:def:crs:EPSG::4326`
traz eixo latitude/longitude em alguns servidores e longitude/latitude em outros, e o erro só aparece no mapa.
O que o serviço declara (`DefaultCRS` do WFS, `storageCrs` do OGC API) fica na ficha da camada; a tabela fica
em 4326. Quando a página vem em GML, a conversão local para GeoJSON já sai em 4326 (RFC 7946) e isso está
escrito no código como decisão (`-t_srs EPSG:4326` explícito), não como padrão de biblioteca.

### 4. Tipo de atributo é o DECLARADO pelo serviço

Depois da carga, cada coluna é levada ao tipo que o serviço declarou (`DescribeFeatureType` no WFS,
`/queryables` no OGC API). Sem isso um `xsd:int` chega como `text` ou como `bigint` conforme o palpite do GDAL
sobre a amostra. Quando o `ALTER` não converte, a coluna fica como está e um aviso nomeado entra na
procedência — nunca se descarta linha para o tipo bater. Quando o serviço não declara nada (`/queryables` é
opcional na Parte 1 do OGC API), o tipo vem de uma amostra e `origem_do_tipo` diz `amostra`: inferido nunca é
apresentado como declarado.

### 5. Modo referenciado com cache de 30 s, no processo

O cache é curto de propósito: o valor da camada referenciada é ser ao vivo, e guardar por muito tempo trocaria
o problema (rajada de requisições no órgão) por outro pior (dado velho servido como atual). Ele mora no
processo, não em Redis: dois processos de API podem devolver respostas de instantes diferentes dentro da mesma
janela de 30 s, e isso está escrito aqui e no MANUAL. Editar ou apagar a conexão esquece o que ela cacheou.

### 6. A cópia não ganha rota própria

Ela é o job `conexao.copiar_vetor`, criado por `POST /api/jobs` como toda tarefa pesada — assim herda fila,
cota, cancelamento, log, progresso e limite de memória, em vez de reimplementar os seis. As rotas novas são só
as três de leitura do modo referenciado (`/colecoes`, `/colecoes/{c}/campos`, `/colecoes/{c}/feicoes`).

### 7. Válvula de teste na defesa de SSRF

A regra do laço é que a suíte nunca dependa de serviço de terceiro para dar verde. Para testar o conector com
um WFS e um OGC API de verdade, eles sobem no loopback — que a validação de SSRF bloqueia, e deve bloquear.
A saída é `PLAT_TESTE_CONEXAO_ALVOS`, uma lista de pares `host:porta` exatos, aceita SÓ fora de produção
(mesma regra de `app.auth.sessao.ajuste_de_teste`, item L0-02) e ignorada com aviso em `producao`. A folga é a
menor possível: par exato, não faixa nem host inteiro; e nada mais da validação é dispensado — esquema,
userinfo, revalidação de cada redirecionamento e o pino de IP contra rebinding continuam valendo. Uma porta
não declarada no loopback (8150, por exemplo) segue recusada com a variável ligada, e isso é testado.

## Fronteira honesta (o que este item NÃO entrega)

- **WFS 1.0/1.1**: só 2.0.0, que é quem tem `STARTINDEX` e `numberMatched`. Um serviço 1.1 é recusado com
  motivo nomeado, não atendido pela metade.
- **Filtro além de bbox e datetime**: nada de CQL2 nem de `Filter` OGC. É o item L6-02-n.
- **Agendamento da cópia**: o job existe e é agendável pelo relógio do L0-05, mas a tela e a política de
  reexecução periódica são o item L6-02-k.
- **Desenho da camada referenciada no mapa**: o item L6-02-b.
- **Escrita de volta (WFS-T)**: fora de escopo, e não está no portão.
- **OGC API - Features Parte 2 (CRS negociado)**: `/items` é sempre lido em CRS84, como manda a Parte 1.
