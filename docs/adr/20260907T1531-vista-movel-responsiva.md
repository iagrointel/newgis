# ADR — vista móvel do documento de construtor: reflow automático ou lista manual (item L5-15)

## Contexto

O item L5-08-editor-arrasto grava `corpo.nos` numa lista plana, com largura em COLUNAS da grade de 12
(1..12), e não tem opinião nenhuma sobre o que acontece quando a mesma tela abre num celular. A hipótese do
item L5-15 (regra observada em produtos de dashboard como o ArcGIS Dashboards: largura ≤ 600 px carrega uma
vista de celular) propõe duas saídas possíveis: (a) cada documento tem uma vista de celular PRÓPRIA, com
elementos e posições diferentes da vista de desktop, ou (b) o documento herda um reflow automático (a grade
de 12 colunas vira 1 coluna, sem configuração nenhuma).

## Decisão

As duas convivem, com REGRA DE PRECEDÊNCIA clara:

1. **Reflow automático é o padrão** (`corpo.vista_movel` ausente, ou `manual: false`): puro CSS
   (`web/estilo/visualizador.css`), grade de 12 colunas vira 1 coluna a ≤ 600 px, TODOS os nós continuam
   presentes, na mesma ordem/aninhamento do documento. Nenhum widget desaparece — é o que garante a
   refutação do item ("adversário abre em 360×640 e lista widget cortado ou inacessível").
2. **Vista móvel manual** (`corpo.vista_movel.manual: true`) é uma lista de override — `corpo.vista_movel.
   nos`, mapa id-de-nó → `{oculto, ordem, largura_colunas}` — que PREVALECE sobre o reflow quando presente.
   Um nó marcado `oculto` simplesmente não entra no DOM da vista móvel: é uma escolha deliberada de quem
   editou o documento (como remover um gráfico só de desktop numa vista mobile), não um acidente de layout.

**D1 (limite deste item): só nó de RAIZ recebe override.** Um contêiner aninhado herda o reflow do próprio
pai. Duas árvores de aninhamento por documento (uma para desktop, outra para celular) multiplicariam a
complexidade do editor por um fator que a hipótese do item não pede — o precedente citado (Dashboards) só
fala em elementos/posições diferentes, que a vista de raiz já cobre. Se um item futuro precisar de override
dentro de contêiner, isso é uma extensão aditiva do mesmo formato (`vista_movel.nos` continua um mapa por
id), não uma reescrita.

## Esquema

`corpo.vista_movel` entrou no esquema de grafo (`028_documento_grafo.sql`) na versão 3
(`db/migracoes/20260907T1505_vista_movel.sql`), ao lado de `nos`/`ligacoes`/`mapas`/`mapa_id`. Chave
opcional — documento sem ela continua válido, e a leitura preenche o padrão explícito
`{"manual": false, "nos": {}}` (`app/catalogo/documento.py::_migrar_app_v2_v3`/`_migrar_painel_v2_v3`), na
mesma disciplina que a 028 já usava para `nos`/`ligacoes` quando eram `corpo: {}`.

`validar_grafo` ganhou duas regras novas, ao lado da checagem de `ligacoes` pendente que já existia (JSON
Schema puro não expressa "esta chave é um id que existe em `nos`" nem "este id não tem `pai`"):
- `referencia_pendente`: chave de `vista_movel.nos` que não é id de nenhum nó do documento;
- `vista_movel_fora_da_raiz`: chave que é um id real, mas de um nó que TEM `pai` (viola D1).

## Pré-visualização por dispositivo (construtor)

Iframe de MESMA ORIGEM (precedente Puck — pré-visualização de página dentro do próprio editor, sem sair
dele) carregando `/visualizar?preview=1`, com três larguras FIXAS de container (celular 375, tablet 768,
desktop 1440) — nunca o viewport real do navegador. O documento em edição chega por `postMessage`
(`{tipo:'plat-documento-preview', documento}`, checado por origem no visualizador), nunca por navegação:
salvar não é pré-requisito para ver o efeito de uma mudança.

## Arrasto por toque

O L5-08 já tinha estabelecido, medindo: **o HTML5 Drag and Drop nunca dispara em toque** — por isso aquele
item só deu alternativa de toque SEM gesto (botão "Adicionar", menu "mover para"). A hipótese deste item
pede o gesto de verdade em tablet ("arrastar por toque testado"), então `web/js/editor/arrasto.js` ganhou um
SEGUNDO caminho por Pointer Events, ao lado do HTML5 DnD (que continua servindo o mouse): limiar de 8 px
antes de assumir o gesto (para não quebrar o toque simples de seleção), ghost visual seguindo o dedo,
`elementFromPoint` para achar o alvo de soltura entre os mesmos elementos já registrados por `ligarAlvo`. A
alternativa por menu/botão do L5-08 continua valendo, lado a lado — nenhuma removida.

## Rejeitado

- **Duas árvores de documento** (uma por breakpoint): complexidade que a hipótese não pede (D1 acima).
- **Largura móvel por nó como layout multi-coluna no celular**: o portão exige "sem rolagem horizontal" e
  "mapa visível" em 360×640 — várias colunas nessa largura arrisca as duas coisas. `largura_colunas` do
  override existe no esquema para uso futuro (ex. tablet como faixa própria), mas a vista ≤ 600 px sempre
  renderiza 1 coluna, ignorando esse campo visualmente por ora (documentado em `visualizador.js`).
- **SortableJS/dnd-kit/interact.js para o toque**: mesma decisão do L5-08 (0 byte de biblioteca de arrasto)
  — a mecânica de toque é pequena o bastante (um limiar, um ghost, um `elementFromPoint`) para não pagar o
  custo de uma dependência nova.
