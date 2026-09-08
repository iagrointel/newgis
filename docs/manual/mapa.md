---
id: mapa
titulo: Mapa
titulo_en: Map
titulo_es: Mapa
resumo: "visualização de camadas do inquilino sobre mapa-base local, com busca de endereço"
resumo_en: "visualization of tenant layers over a local basemap, with address search"
resumo_es: "visualización de capas del inquilino sobre mapa-base local, con búsqueda de dirección"
classe: tela
pagina: mapa.html
caminho: /mapa
e2e: tests/e2e/test_mapa.py
captura: L2-01-a-basemap-local-pmtiles_mapa.png
e2e_captura: "{ITEM}_mapa.png"
palavras: [mapa, camadas, basemap, pmtiles, escala, endereco, geocodificar]
palavras_en: [map, layers, basemap, pmtiles, scale, address, geocode]
palavras_es: [mapa, capas, basemap, pmtiles, escala, direccion, geocodificar]
---

## Mapa

A tela Mapa mostra as camadas do inquilino sobre um mapa-base servido da própria máquina (PMTiles
local): nada depende de serviço de mapa de terceiros.

1. O painel de camadas liga e desliga cada camada e ajusta transparência.
2. A busca de endereço usa o geocodificador local (CNEFE do IBGE) quando instalado.
3. A régua de escala e o nível de zoom acompanham o movimento; a URL guarda a posição para
   compartilhar a vista.

O mapa-base cobre o território nacional nas escalas carregadas pela instalação; onde não há
tmestre local, o quadro fica vazio em vez de chamar serviço externo.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_mapa.py`) contra a versão atual.
