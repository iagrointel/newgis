# ADR 20260908T1230 — layout de impressão: documento, compositor e Export Web Map Task (L2-12-b)

## Contexto

O visualizador imprime uma faixa sobre o canvas (L2-01, `impressao.js`); não há documento de layout, elementos
cartográficos posicionados, modelos, exportação vetorial nem o endpoint que o widget Print da Esri chama. O
motor de render do L2-12-a (pool de chromium, `app/render/motor.py`) existe no ramo `wt/il212amotor`, mas não em
master, e desenha só o mapa-base (501 para mapa com camadas: à época não havia servidor de tiles).

## Decisão

1. **Tipo de item `layout`** (migração `20260908T1203_layout.sql`): papel (A4-A0, carta), orientação, margens e
   elementos em MILÍMETROS — quadro de mapa (extensão fixa ou escala 1:N, rotação, principal/localização),
   legenda, barra de escala, seta de norte (verdadeiro/grade), grade (UTM em metros ou geográfica em GMS),
   título/texto com expressões, imagem (logotipo), tabela de atributos (seleção), data, atribuição.
   `app/layout/modelos.py::validar` nomeia o campo que reprova; o mesmo esquema está no `tipo_item`. Modelos
   padrão em código; modelos do inquilino = itens `layout` com `modelo: true`. Sem tabela nova.
2. **Geometria declarada** (`app/layout/geometria.py`): Web Mercator do MapLibre (mundo = 512·2^z px), escala
   1:N ↔ zoom no DPI pedido e na latitude do centro, barra "redonda", UTM por `pyproj`, convergência meridiana.
   A escala impressa e o desenho usam a MESMA conta — a régua do adversário mede isso no PDF.
3. **Compositor** (`app/layout/compor.py`): elementos → primitivas em mm → HTML (texto como `<div>`, formas num
   único `<svg>` de página, imagens `<img>`) → WeasyPrint (`@page` exato, texto selecionável) → PDF; PNG/JPG pelo
   PyMuPDF; SVG direto das primitivas. O quadro é raster no DPI pedido, com TETO de pixels
   (`LAYOUT_QUADRO_PIXELS_MAX`): acima disso o quadro sai no teto e o relatório declara o DPI efetivo — "vetor
   puro" do mapa fica FORA nesta fase, como o item já dizia. Legenda paginada por colunas e truncada com aviso.
   Atribuição do mapa-base é obrigatória: entra sozinha quando o layout não a tem.
4. **Quadro pelo motor do L2-12-a** copiado por arquivo de `wt/il212amotor` (900c0b16), sem `app/mapas` (que
   duplica o item `mapa` de master): uma página headless própria (`web/render_layout_mapa.html`) recebe um token
   interno assinado com payload (inquilino, usuário, camadas) e o troca por um estilo com tokens de tile cunhados
   no ato (`/api/render/layout/estilo`, só do host de loopback). Assim o quadro desenha camadas do catálogo via
   Martin — a fronteira do L2-12-a cai porque os tiles agora existem. `PLAT_RENDER_IGNORAR_HTTPS` aceita o
   certificado autoassinado da trilha; `PLAT_RENDER_BASE_URL` diz onde a página vive quando não é a URL pública.
5. **Job `layout.exportar`** (worker; pool de chromium próprio do processo) guarda o arquivo como objeto do
   inquilino (classe `layout_exportacao`) e devolve sha256, URL e relatório. `POST /api/layouts/exportar` valida
   antes de enfileirar; `POST /api/layouts/previa` compõe um PNG ≤ 96 DPI na hora (quadro cinza ou pelo motor).
6. **Esri**: `/rest/services/Impressao/GPServer` com `Export Web Map Task/execute` (Web_Map_as_JSON → layout do
   modelo → composição síncrona → `Output_File.url` servida por `/saida/{sha}?token=`) e
   `Get Layout Templates Info Task/execute`. Camada sem equivalente nosso (Living Atlas etc.) vira aviso "fora do
   quadro", nunca cópia; `baseMap` externo vira o mapa-base local com aviso.
7. **Painel Layout** no visualizador (`web/js/mapa/layout.js`, atalho `y`): modelo → elementos por FORMULÁRIO em
   mm (o arrasto é o L5-08) → prévia → exportação com progresso pelo canal de eventos → gravar layout/modelo.

## Consequências

- O mapa do quadro é a definição da tela (camadas ligadas, opacidade, base, vista); o item `mapa` de master só
  guarda desenho, então `mapa_de_item` lê `corpo.camadas` quando existir e o painel manda a vista inline.
- Rotação do quadro é aplicada no desenho (bearing), mas a grade não é desenhada sobre quadro rotacionado
  (declarado no relatório). Expressões de campo de feição (`{campo:x}`) ficam para o L5-29 (mantidas literais).
- Duas cópias do motor de render podem coexistir quando `wt/il212amotor` juntar: os arquivos copiados são
  idênticos ao commit de origem, e `app/render/rotas.py` daquele ramo (que depende de `app/mapas`) não veio.
