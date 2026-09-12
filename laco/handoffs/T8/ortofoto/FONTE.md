# Ortofoto de São Paulo usada na prova do caminho de imagem

## O que é

Ortofoto do **Mapeamento Digital da Cidade de São Paulo (MDC)**, publicada pela Prefeitura de São
Paulo no portal GeoSampa.

| | |
|---|---|
| resolução | **10 cm** em área urbanizada e periférica; 20 cm em área rural |
| sistema de referência | SIRGAS 2000 / UTM 23S (EPSG:31983) |
| licença | **CC0** — declarada no portal de dados abertos da Prefeitura |
| responsável | Prefeitura de São Paulo / PRODAM |

## Endereços

- Conjunto no portal de dados abertos, onde a licença CC0 está declarada:
  https://dados.prefeitura.sp.gov.br/dataset/ortofotos-do-mapa-digital-da-cidade-de-sao-paulo-mdc
- Metadado do voo de 2020:
  https://metadados.geosampa.prefeitura.sp.gov.br/geonetwork/srv/api/records/892c862e-f564-4b1c-a3d0-9d28052e5d58
- WMS de raster (camadas `Orto_MDC` e `Orto_PMD_RGB_2017`):
  http://raster.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wms
- WFS com a grade oficial de folhas (`geoportal:quadricula_orto_2020`, código em `cd_quadricula`):
  http://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs

## Como o recorte foi obtido, e o que deu errado

Pedidos `GetMap` de 4000 × 4000 px em EPSG:31983, cada um cobrindo 400 m de terreno — o que dá
exatamente 10 cm por pixel. O georreferenciamento veio de *worldfile* escrito por nós, e é exato
porque a caixa de cada pedido é nossa; foi conferido contra o `gdalinfo` de uma folha.

⛔ **Fomos bloqueados pela PRODAM.** Quatro pedidos simultâneos contínuos durante 14 minutos
levaram o serviço a cortar nosso endereço: a resposta passou a vir com `Código de Bloqueio:
13447961135437618666` e o host `raster.geosampa` parou de responder, enquanto `wfs.geosampa`
continuou de pé. Isso aconteceu com 88 das 625 folhas colhidas.

Duas lições, e as duas valem para qualquer colheita futura:

1. **Antes do bloqueio o serviço já avisava.** Com 4 pedidos em curso, dois pedidos extras
   devolveram PNG em branco com HTTP 200 — 440 bytes, que é o tamanho de um 4000 × 4000
   inteiramente transparente. Degradação silenciosa é o sinal de que se passou do ponto, e o
   guarda de tamanho mínimo do colhedor foi o que impediu esse branco de entrar no mosaico.
2. **O caminho certo para volume não é o WMS**, é o download de arquivo por folha da grade
   oficial. A grade sai do WFS (375 folhas dentro do quadrado de 100 km²); o endereço de download
   por folha não foi decifrado antes do bloqueio.

Nada foi feito para contornar o bloqueio, e nada deve ser.

## O recorte que ficou

As três primeiras colunas saíram completas, e formam um retângulo contíguo com a forma de uma
linha de voo:

| | |
|---|---|
| caixa | E 325.000–326.200, N 7.388.000–7.398.000 (EPSG:31983) |
| terreno | 1,2 km × 10 km = **12,0 km²** |
| pixels | 12.000 × 100.000 = **1,2 gigapixel** |
| GeoTIFF sem compressão | **3.699.433.104 bytes = 3,70 GB** |
| bandas | 3 (o alfa do WMS foi descartado: é 255 em toda a área com dado) |

O mosaico usa **só** o retângulo cheio. As 13 folhas soltas da quarta coluna ficaram de fora de
propósito: área vazia comprime a quase nada e inflaria a razão de compressão, que é justamente o
número que vai para a conta.
