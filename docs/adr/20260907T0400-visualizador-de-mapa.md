# Visualizador de mapa: como a camada do catálogo chega ao navegador (item L2-01-mapa-web)

Nomeado por carimbo de tempo (ADR 0014). Complementa o ADR 0020 (papel de leitura e tile por token) e o
ADR de 20260907T0235 (verificação de token antes do Martin), que já estavam escritos e cujo código foi
trazido para este ramo.

## Contexto

O conceito da linha (`laco/decomposicao/L2_CONCEITO.md`) já decidiu: estilo em MapLibre Style Spec pura
com bloco `plat_construtor` (C2), tiles vetoriais por função de PostgreSQL servida pelo Martin (C3),
token na URL para cliente externo (C9), CRS nativo preservado e exibição em Mercator (C11). Faltava
decidir três coisas que só aparecem quando o navegador entra na história.

## Decisão 1 — o navegador entra por sessão e recebe um token cunhado de 12 horas

O Martin autoriza pelo `query_params` da função de tile: precisa de um token de serviço na URL. O
navegador do usuário entra por cookie de sessão. Em vez de aceitar cookie no caminho do tile (que
obrigaria a validação de sessão a cada tile e abriria CSRF de leitura), `GET
/api/mapa/camadas/{id}/tilejson` cunha um token de serviço com escopo `camada:ler:<uuid>` — UMA camada,
12 horas — e o devolve dentro de um TileJSON 3.0.0 padrão. O token anterior do mesmo usuário para a mesma
camada é revogado na mesma transação, então reabrir o mapa não acumula tokens. Consequência aceita: o
token viaja na URL do tile e aparece no histórico do navegador daquela aba; por isso é de escopo estreito
e de vida curta, e é revogável como qualquer outro token na tela de tokens.

## Decisão 2 — uma implementação de autorização, duas portas

`app/tiles/rotas.autorizar(caminho, token, ip, origem)` é a única implementação. Ela é chamada por:

* `GET /internal/tiles/verificar` — o `auth_request` do nginx, para quem quiser que o nginx repasse o
  tile direto ao Martin, sem Python no caminho;
* `GET /tiles/{esquema}/{funcao}/{z}/{x}/{y}` — o repasse da própria plataforma, que é o caminho usado
  pelo visualizador e por qualquer instalação sem nginx na frente (o appliance do Degrau 0).

Duas portas com duas cópias da regra divergem no primeiro conserto. Uma função só, dois chamadores.

Custo medido do repasse em Python: tile z8 da camada de 1 milhão de feições em **406 ms na mediana a
frio** e **21 ms a quente** (12 pedidos cada, `tests/api/test_mapa_api.py`), contra 294-568 ms medidos
direto no Martin. O caminho por nginx continua disponível e é o que se liga quando a carga justificar.

## Decisão 3 — a legenda nasce da simbologia, no servidor

`app/mapa/simbologia.py` tem uma função `classes()` que devolve rótulo, cor e teste por classe. As duas
saídas do módulo — as camadas de estilo (MapLibre) e as entradas de legenda — são construídas dessa mesma
lista. Não existe caminho em que a legenda diga uma cor e o mapa pinte outra; o teste
`tests/unit/test_simbologia_mapa.py` compara as duas listas de cores. Vocabulário fechado: `simples`,
`valores_unicos`, `intervalos`; qualquer outro tipo é recusado, nunca "cai no padrão em silêncio".

## Decisão 4 — impressão composta no navegador, sem biblioteca de PDF

O portão pede PNG e PDF com escala e norte. O caminho escolhido é compor no próprio canvas do MapLibre
(`preserveDrawingBuffer: true`) uma faixa com título, escala numérica 1:N, barra de escala, seta de norte
e atribuição; o PNG é o canvas, e o PDF é uma página A4 paisagem com esse canvas em JPEG dentro de um
escritor de PDF de 100 linhas (`web/js/mapa/pdf.js`, `/Filter /DCTDecode`). Não se trouxe biblioteca de
PDF: para uma página com uma imagem, o formato é pequeno, e uma dependência de terceiro custaria linha em
`VERSOES.txt`, sha256 e auditoria. A prova não é a nossa palavra: o e2e converte o PDF gerado com
`pdftoppm` (Poppler) e confere que a página tem desenho, e lê o texto com `pdftotext`.

Limite declarado: uma página, uma imagem, fontes só as 14 padrão do PDF, texto rebaixado para WinAnsi.
Impressão em tamanho de folha maior que a tela, com layout de peça cartográfica (moldura, grade,
legenda impressa), é o serviço de renderização do lado do servidor (`plat-render`, conceito C10, item
L5-29) — **não está neste item**.

## Decisão 5 — geocodificar por GET

A caixa de pesquisa é leitura. O POST `/api/geocodificar` passa pela checagem de origem da porta de
escrita sob cookie (ADR 0002 seção 5.3) e recusa, corretamente, sempre que a URL pública configurada não
é a do navegador — o que é a regra em ambiente de teste e no appliance. Acrescentou-se `GET
/api/geocodificar` com o mesmo contrato, reusando o mesmo manipulador. O POST continua valendo.

## Duas armadilhas medidas (ficam registradas porque custaram tempo)

1. **`attribution: undefined` derruba a fonte inteira no MapLibre.** A especificação da fonte é validada;
   uma chave presente com valor `undefined` faz a fonte não ser criada, em silêncio (só um evento
   `error`), e todas as camadas dela falham depois com `source "..." not found`. Chave opcional só entra
   no objeto quando tem valor.
2. **Repassar `Content-Encoding: gzip` com corpo já descompactado.** O Martin gzipa o MVT e o cliente
   HTTP descompacta ao ler o corpo; repassar o cabeçalho junto entrega ao navegador um tile que ele tenta
   inflar de novo (`Error -3 while decompressing data`). O repasse pede `Accept-Encoding: identity` ao
   Martin e nunca copia `Content-Encoding`; quem comprime na saída é o nginx, uma camada só.

## O que fica de fora deste item

Camada raster por tiles (o TiTiler é o L1-02), PMTiles como fonte de camada de dado do inquilino (só o
mapa-base usa PMTiles hoje), construtor de simbologia na tela (L5-27), tabela de atributos (L2-01-g),
seleção e filtro (L2-01-h), gráficos (L2-01-i), cortina e tempo (L2-01-j), desenho e anotação (L2-01-k),
exportação a partir do mapa (L2-01-l), galeria de mapas base por inquilino (L2-01-e) e o documento de
mapa persistido como item do catálogo (L2-01-a-documento-mapa, em outro ramo). Este item entrega o motor
e os controles; os sub-itens acrescentam as telas.
