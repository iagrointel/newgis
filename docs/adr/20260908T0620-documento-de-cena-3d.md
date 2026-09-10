# Documento de cena 3D: um tipo de item, o mesmo motor de mapa, slides no corpo

- Item: L2-09-b-cena-extrusao-slides
- Data: setembro de 2026
- Estado: aceito

## Contexto

A plataforma precisa de uma cena 3D comparável à do visualizador de cenas do produto que se quer
substituir: terreno, volumes com altura vinda de um atributo, iluminação por data e hora e vistas
salvas ("slides"). O catálogo já previa o tipo de item `cena` desde a migração 011, com envelope vazio.

## Decisão

1. **A cena é um item do catálogo, tipo `cena`.** Nenhuma tabela nova, nenhuma rota nova de documento:
   criar, ler, editar, versionar, publicar e comparar versões são as rotas genéricas de `/api/itens`
   (L0-03 e L5-05). O que a migração deste item faz é trocar o envelope vazio pelo esquema JSON do
   documento — câmera, terreno, iluminação, atmosfera, camadas e slides.
2. **`esquema_versao` continua 1.** Todo documento que existia (corpo vazio) continua válido no esquema
   novo, e nenhum campo dentro de `corpo` é obrigatório. Sem documento inválido, não há migração de
   leitura a escrever.
3. **O que o JSON Schema não expressa fica em `app/cena/documento.py`** e é chamado pela MESMA porta que
   já valida o grafo dos construtores (`app/catalogo/documento.validar_grafo`), para que exista um só
   lugar por onde um item passa antes de ser gravado: id repetido, slide que cita camada ausente,
   extrusão sem altura, base acima do topo.
4. **Um motor de mapa só.** Terreno é `setTerrain` sobre uma fonte `raster-dem`; volume é
   `fill-extrusion`; céu e névoa são `setSky`; luz é `setLight`. Nenhuma segunda biblioteca 3D entra
   no visualizador. Modelos glTF/IFC/3D Tiles ficam para o L2-09-c, que já nasce com essa restrição.
5. **A posição do Sol é calculada no servidor** (`app/cena/sol.py`, algoritmo do NOAA) e exposta em
   `GET /api/cena/sol`. Uma implementação só, testável contra uma segunda fórmula independente (a do
   Astronomical Almanac, escrita dentro do teste). O navegador pede o ângulo e o entrega ao MapLibre.
6. **Slide é vista salva dentro do corpo do documento**: nome, câmera, camadas visíveis, hora do dia,
   exagero do terreno e uma miniatura JPEG gerada do próprio canvas. Restaurar usa `jumpTo`, não
   `flyTo` — a vista restaurada é a mesma, não uma aproximação com animação.
7. **A cena consome o terreno por URL de ladrilho**, não gera terreno. Quem produz os ladrilhos
   terrain-RGB é o trabalho do item L2-09-a (`app/relevo/`); a cena guarda a URL, a codificação, o
   tamanho do ladrilho e o exagero. Essa é a costura entre os dois itens.

## Consequências

- Quem já sabe usar o catálogo já sabe versionar, compartilhar e publicar uma cena: nada de novo a
  aprender e nada de novo a manter.
- Altura negativa, nula ou não numérica é presa em 0 na expressão de pintura (`max` + `to-number` com
  reserva). Sem isso o MapLibre desenha caixa invertida em silêncio, sem erro nenhum.
- Ficam FORA, e declarados: globo (a projeção é a do MapLibre), sombra projetada exata, corte de malha
  e linha de visada sobre malha — os três dependem de geometria de malha, que é do L2-09-c/L2-09-d.
  A iluminação move a luz da cena; ela não projeta sombra de um volume sobre o outro.
- A medição de altura é a diferença de cota entre dois pontos, onde a cota é o terreno mais o topo da
  extrusão sob o cursor. É medida do que está desenhado, não leitura de uma coluna do banco.
