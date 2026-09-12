# Ortofoto de 10 cm pela nossa pilha: o que foi medido

Análise / beta privado. Todo número abaixo foi medido nesta máquina em 12/09/2026, pelo
caminho que um cliente usa. Onde há conta em vez de medição, está escrito.

## A imagem

| | |
|---|---|
| fonte | Ortofoto do Mapa Digital da Cidade de São Paulo, **licença CC0** |
| área | 12,0 km² (faixa de 1,2 × 10 km) |
| resolução | 10 cm |
| pixels | 12.000 × 100.000 = **1,20 gigapixels** |
| sistema de referência | SIRGAS 2000 / UTM 23S (EPSG:31983) |
| como vem do voo | **3,70 GB** em GeoTIFF sem compressão |

## O que a pilha fez com ela

| etapa | medida |
|---|---|
| envio, em 221 partes de 16 MiB | 100,8 s a 37 MB/s |
| conversão, medida pelo próprio job | 43,8 min |
| job de ponta a ponta | 44,0 min |
| COG visual (JPEG) | **433 MB** |
| COG científico (ZSTD, dtype original) | 1,56 GB |
| **razão do visual sobre o bruto** | **8,5 × menor** |
| pirâmide servida | 15.234 ladrilhos, zoom 14 a 20 |
| ladrilho servido, primeira vez | 197 ms (mediana) |
| ladrilho servido, em cache | **24 ms** |
| peso do ladrilho | 182 kB |

⚠ O tempo de conversão desta medição é limitado pelo DISCO, não pela pilha: o volume
desta máquina mede 25 MB/s com 100 % de utilização, porque é compartilhado com bancos
de cliente. Numa máquina dedicada o mesmo trabalho é outro número, e eu não o medi.

## A conta, por ano

Tarifa da Esri lida em `doc.arcgis.com/en/arcgis-online/administer/credits.htm` em
12/09/2026. Crédito a R$ 1.808 por 1.000 pelo Catálogo SGD/MGI v2.0 — é preço de catálogo
federal, não preço de balcão da Esri, que não é publicado em dólar.

| o cliente hospeda no ArcGIS Online | créditos/ano | R$/ano |
|---|---|---|
| a imagem crua como camada de ladrilho | 53 | R$ 96,32 |
| a imagem crua como **imagem dinâmica** (1,2/GB/mês + 10 créditos/dia) | 3.703 | **R$ 6.696** |
| só o COG, como camada de ladrilho | 6 | R$ 11,28 |
| *se* fosse feição editável do mesmo tamanho (240 créditos/GB/mês) | 1.248 | R$ 2.256 |

Aqui: guardamos 5,70 GB (a crua mais os dois COG). A máquina de objetos custa
€ 449 por mês com 132 TB úteis, ou € 3,40
por TB por mês, então o disco desta imagem sai por **R$ 1,37 por ano**
(PTAX de 2026-09-11, EUR/BRL 5.9085).

A frase é essa: **o ArcGIS Pro e o ArcGIS Online continuam sendo a tela. Muda o lugar do**
**arquivo.** O cliente não põe a imagem lá dentro; ele aponta para uma URL nossa.

⚠ **O que esta medição obriga a corrigir na fala.** Guardar estes 3,70 GB como camada de
ladrilho no ArcGIS Online custa R$ 96,32 por ano. É troco. Para UMA
imagem pequena, compressão não é argumento de custo. O que pesa no ArcGIS Online é outra
coisa, e são duas:

1. **a taxa diária da imagem dinâmica** — 10 créditos por dia no degrau mais baixo,
   R$ 6.599 por ano, **independentemente do
   tamanho da imagem**. É um piso por imagem servida, e some se a imagem não está lá;
2. **o volume**, quando não é um recorte de 12 km² e sim uma cidade — a seção seguinte.

A compressão continua valendo, mas o que ela compra é DESEMPENHO e disco, não crédito:
433 MB em vez de 3,70 GB é o que faz o ladrilho sair em dezenas de milissegundos.

## Estender para a cidade inteira — isto é CONTA, não medição

O voo de 2020 de São Paulo cobre 1.521 km² a 10 cm, que é 127 vezes
esta faixa. Aplicando a razão medida de 8,5 ×:

| | conta |
|---|---|
| cru da cidade | 469 GB |
| COG visual da cidade | 55 GB |
| hospedar o cru como imagem dinâmica no AGOL | R$ 18.807/ano |
| disco aqui | R$ 174/ano |

⚠ A razão de compressão de uma cidade inteira NÃO é a desta faixa: telhado, vegetação e
asfalto comprimem de maneiras diferentes, e esta faixa é de um recorte só. A conta serve
para dar ordem de grandeza numa conversa, não para entrar em proposta.

## Para o parceiro testar

⛔ O token foi trocado por `<TOKEN>` nesta cópia do repositório. A versão com o
endereço completo fica em `/mnt/pgdata/plat-orto/DOCUMENTO.md`, modo 600, fora do git.

No ArcGIS Pro, *Insert → Connections → New WMTS Server*, ou no ArcGIS Online,
*Add Layer from Web → WMTS*. O token está no caminho e vale só para esta imagem.

```
https://sistema.iagrointel.com/svc/<TOKEN>/raster/75747924-c15e-4968-a076-4c5a27196520/wmts/1.0.0/WMTSCapabilities.xml
```

Forma KVP, que o diálogo do Pro às vezes prefere:

```
https://sistema.iagrointel.com/svc/<TOKEN>/raster/75747924-c15e-4968-a076-4c5a27196520/wmts?SERVICE=WMTS&REQUEST=GetCapabilities
```

E como ImageServer da Esri:

```
https://sistema.iagrointel.com/svc/<TOKEN>/rest/services/75747924-c15e-4968-a076-4c5a27196520/ImageServer
```

Atenção ao copiar: **cole, não redigite**. O token distingue maiúscula de minúscula e contém `_`, `l`, `O`, `0`, que se confundem à leitura.
Uma URL redigitada já falhou com 403, e o ArcGIS Pro mostra 403 como "Invalid Path".

## O que NÃO está provado

- Nada disto foi aberto no ArcGIS Pro por nós: não temos o Pro nesta máquina. O AGOL
  aceitou uma camada nossa; o Pro é teste do parceiro.
- A faixa tem 12 km², não os 100 km² pretendidos: **fomos bloqueados pela PRODAM** por
  excesso de pedidos ao WMS da Prefeitura, e paramos em 88 das 625 folhas. O caminho
  certo para volume é o download por folha da grade oficial, que não foi decifrado.
- O tempo de conversão é o desta máquina, com disco compartilhado a 25 MB/s.
- A extensão para a cidade é aritmética, e está marcada como tal.
