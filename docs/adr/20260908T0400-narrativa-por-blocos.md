# ADR 20260908T0400 — narrativa por blocos

Item L5-04-a-blocos-de-conteudo (linha L5, pai L5-04-storymap). Editor de narrativa: documento = lista de blocos
com id, onze tipos (capa, texto, imagem, vídeo, áudio, mapa com vista salva, tabela, botão, separador, incorporar,
app/painel da plataforma), reordenação por arrasto e por teclado, texto alternativo obrigatório, publicação por link.

## Decisões

1. **Nenhum editor novo.** A narrativa é um item `narrativa` com o envelope de documento do L5-05 (`corpo.nos`
   lista plana com ULID, `ligacoes` vazio) e é editada pelo editor de arrasto compartilhado do L5-08 com uma
   PALETA própria (`web/js/editor/paleta_narrativa.js`): todo bloco é um nó de 12 colunas sem filhos, e
   reordenar é mover na lista — arrasto (soltar sobre um nó = entrar antes dele) e teclado (Alt+setas) chamam
   o mesmo `mover`. Foi preciso acrescentar ao editor dois ganchos genéricos: `def.personalizados` +
   `def.controle` (um campo do esquema desenhado pela paleta, com `api.propriedade` gravando pelo mesmo
   `definirPropriedade`) e `def.resumo`; e uma área de texto para strings longas. Nada disso sabe o que é
   narrativa.
2. **Leitura é outra forma do mesmo documento.** `web/js/narrativa/leitor.js` desenha cada bloco como conteúdo;
   é usado por `/executar?item=` (autor, sessão) e pela página publicada `/p/<inquilino>/<slug>` do L5-14
   (anônima, sem casca). O executor de app (L5-01-a) e o leitor não se conhecem; a tela `/executar` só escolhe
   pelo tipo do item.
3. **Vista salva do mapa = caixa + proporção.** O bloco grava `vista = {bbox, centro, zoom, rotacao,
   proporcao, camadas}` pelo controle do painel (um MapLibre no painel de propriedades; "Usar esta vista"). Na
   leitura, o quadro recebe `aspect-ratio` igual à proporção salva e `fitBounds(bbox, padding 0)` com zoom
   fracionário: em qualquer largura de viewport a caixa visível é a mesma — é o que faz a deriva ficar bem
   abaixo de 1 % em 1280×800 e 480×900 (medido no e2e; centro/zoom ficam como reserva e leitura humana). Se a
   vista guardasse só centro/zoom, a caixa dependeria do tamanho do quadro e a refutação de dois viewports
   reprovaria por construção.
4. **Texto alternativo é regra do servidor, não só do editor.** `app/catalogo/narrativa.py::problemas_para_publicar`
   corre em `publicacao.publicar` (L5-14) para a família `narrativa`: imagem (ou capa com imagem) sem texto
   alternativo, endereço de mídia/embed fora do próprio servidor sem https, bloco de tipo desconhecido e vista
   incompleta respondem `422 narrativa_nao_publicavel` com a lista `[{bloco, tipo, campo, erro}]`; o rascunho
   grava normalmente (o autor pode salvar pela metade), só a publicação é recusada. O botão Publicar do
   construtor mostra a mensagem bloco a bloco.
5. **Segurança do conteúdo (D23; refutação "injeta HTML no texto").** Markdown → conversor mínimo da casa
   (`web/js/widgets/seguro.js`, L5-01-d) → DOMPurify sem `style/form/input/button`; URL de imagem, vídeo, áudio e
   botão só própria ou https (`urlSegura`); embed sempre `<iframe sandbox>` sem `allow-same-origin` e só https;
   vídeo externo só YouTube (nocookie) e Vimeo por URL de embed reconstruída; tabela é texto célula a célula.
   Nenhum HTML do documento entra por `innerHTML`.
6. **Relações para o token da publicação.** `relacoes.py` extrai `mapa_de_narrativa` e `app_de_narrativa`
   (tipos novos em `plat.relacao_tipo`, migração `20260908T0300_narrativa_tipo.sql`); `camadas_citadas` do L5-14
   percorre narrativa → mapa → camada, então o token da publicação lê exatamente as camadas dos mapas citados.
7. **Base do ramo.** `wt/il514public` (L5-14) e `wt/cx501d` (L5-01-d) foram juntados neste ramo para reusar a
   publicação e os utilitários de segurança; os commits são os mesmos, a fila junta sem conflito.

## Parcial declarado
Camadas do catálogo dentro do bloco de mapa na página publicada anônima: o TileJSON exige sessão; o escopo de
tile pelo token da publicação é a cláusula pendente do próprio L5-14 (depende do L1-02). Na leitura com sessão
(`/executar`) as camadas entram.

## Fora deste item
Blocos imersivos dos StoryMaps (sidecar, slideshow, swipe, map tour, timeline — L5-04-b/c), coleções, temas e
capa com vídeo; editor visual de texto (Quill, opção tardia do D23); exportação estática com mídia embutida.
