# Galeria de mapas base por inquilino (item L2-01-e-mapas-base)

Data: setembro de 2026. Estado: aceita.

## Contexto

A tela `/mapa` nasceu (item L2-01-a) com um mapa base único, fixo no código: um PMTiles local de
Guarulhos, servido pelo próprio nginx por Range HTTP. O produto precisa do que o ArcGIS Enterprise
chama de galeria de mapas base: várias fontes, o administrador escolhe o padrão e a ordem, cada
usuário troca no mapa.

## Decisão

1. **Mapa base é item do catálogo, não tabela nova.** O tipo `mapa_base` entra em `plat.tipo_item`
   (migração `20260907T1649_mapa_base.sql`) e cada mapa base é uma linha de `plat.item`. Com isso
   herda de graça: RLS por inquilino, compartilhamento, versão, evento, busca, soft delete e as
   rotas genéricas `/api/itens` para criar, editar e apagar. As colunas `creditos` e
   `termos_de_uso` do item, que já existiam, passam a carregar a atribuição e a licença da fonte —
   a exigência da ODbL vira campo obrigatório validado, não texto solto no frontend.
2. **A validação do conteúdo é JSON Schema na própria migração**, com `if/then` por `dados.tipo`.
   Não há validador em Python para mapa base: o motor genérico do catálogo já valida todo item
   contra o esquema do seu tipo. Uma cópia Python seria uma segunda verdade a desalinhar.
3. **Quatro fontes abertas de instalação** (`app/mapas_base/semear.py`): PMTiles vetorial local,
   raster do OSM pelo proxy da casa, satélite Sentinel-2 por um TiTiler externo e "nenhum" (fundo
   cor). Licença e proveniência de cada uma em `docs/DADO_DEMO.md`.
4. **O proxy raster do OSM não aceita host de lugar nenhum.** A rota recebe só `z/x/y`, valida os
   três contra a faixa do slippy map e escolhe o host de uma tupla fixa em `app/limites.py`. Não
   existe parâmetro de host, de URL ou de esquema — proxy aberto não é evitado por lista de
   bloqueio, é impossível por construção. A busca ainda sai pelo caminho seguro comum da casa
   (`app.conexao.seguranca.buscar_seguro`) como defesa em profundidade.
5. **Cache do proxy é arquivo em disco, não banco.** Um ladrilho é um `.png` em
   `var/cache/mapa_base_osm/<z>/<x>/<y>.png`, com teto de tamanho e poda do mais antigo por mtime.
   A política de uso do `tile.openstreetmap.org` exige cache e identificação do cliente; ambos
   ficam do nosso lado, o navegador nunca fala com o OSM.
6. **Trocar de mapa base troca o `style` inteiro do MapLibre.** Como `setStyle` descarta toda fonte
   e camada, `web/js/mapa/mapa.js` mantém um registro das camadas operacionais e as reaplica no
   `styledata` seguinte, restaurando centro/zoom/bearing/pitch com `jumpTo`. Quem monta camada por
   cima do mapa usa `window.platMapa.adicionarCamadaOperacional`.

## Consequências

- Um mapa base novo é uma linha de catálogo, não código: o administrador cria por `/api/itens`.
- Só um mapa base padrão por inquilino, garantido por índice único parcial; a troca normal é feita
  em uma transação, e o índice é a rede de última linha.
- A atribuição sobrevive à impressão por regra `@media print` em `web/mapa.css`. O layout de
  impressão completo é o item L2-12, ainda pendente — aqui só se garante que o crédito da licença
  não some no papel.
- O teto de disco do mapa base instalado está em `limites.MAPA_BASE_DISCO_BYTES_MAX`, valor
  interino: a decisão D27 do dono (Protomaps do Brasil inteiro, com o disco da casa a 98 %) segue
  aberta.
