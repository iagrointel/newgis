# Identidade visual do `plat` (item L0-14-identidade-visual)

Estado: análise / beta privado. Decisão de direção do dono em 06/09/2026: **instrumento** — painel escuro por
padrão, denso, cantos retos, âmbar de instrumento no lugar do azul de sistema, número em algarismo de largura
fixa. Este documento fixa o que se vê no produto e por quê; o que se mede está em `tests/medidas/L0-14.json`
(com o comando dentro do JSON) e a página viva é `/estilo` no próprio produto.

Leitor das telas: técnico de SIG e administrador de plataforma, que passa o dia inteiro nelas. Não é consumidor.
Por isso: densidade alta, contraste medido, nada arredondado, nada animado além do giro de "carregando".

## 1. O traço que só este produto tem: a régua

**Todo número que a tela mostra carrega a sua procedência.** De que rota veio, em que instante e, quando
existe, o comando que o gerou. É a regra da casa para documento ("número em documento sai de script, com o
comando que o gerou") levada para a interface. Nenhuma outra plataforma SIG mostra, ao lado da contagem de uma
lista, de onde a contagem veio.

Como se vê:

- um número com procedência tem embaixo uma **régua**: uma linha de base com traços a cada 4 px, em âmbar
  (`.regua` em `web/estilo/base.css`, elemento criado por `web/js/base/regua.js`);
- em hover ou com foco de teclado (`tabindex="0"`) aparece a etiqueta em fonte de dado: `origem GET /api/usuarios
  -> 200 · 41 ms`, `instante 14:32:05 UTC`, `comando curl -sS <url>/saude`; o mesmo texto vai no `aria-label`,
  para leitor de tela — a procedência nunca depende só de hover;
- no rodapé de toda tela com sessão há a **linha de procedência da tela** (`.regua-tela`): as últimas cinco
  chamadas à API, com rota, código HTTP, hora UTC e duração, alimentada por `web/js/base/api.js`
  (`registrarChamada`), que anota toda chamada sem guardar corpo nem cabeçalho de autenticação.

Onde está hoje: contagem no título de cada lista (`cabecalho()` em `layout.js`), faixa "1–50 de 123" da
paginação, versão/commit/ambiente e saúde da página inicial (com o comando de conferência do MANUAL), a razão de
contraste na página `/estilo` (com a fórmula WCAG como comando) e a linha de procedência de toda tela.

Por que este e não outro: o candidato declarado no item era a régua. Foi adotado porque (1) não é decoração, é
a mesma disciplina que a casa aplica a documento; (2) custa pouco por tela (o registro é automático no cliente
da API) e escala com o produto — cada tela nova ganha a linha de procedência sem código; (3) é verificável por
teste (a etiqueta tem de casar com a chamada real). Alternativas consideradas e descartadas: "mapa como fundo de
tudo" (não serve às telas administrativas, que são a maioria) e "marca d'água de coordenadas" (decoração sem
função). A moldura de instrumento (traço em L nos cantos, `.instrumento-moldura`) fica como assinatura
secundária, só em painéis-chave (tela de entrada, seção da régua em `/estilo`).

## 2. Tokens: a fonte única

`web/estilo/tokens.css` é o único arquivo do produto que escreve cor ou medida. Toda outra folha
(`web/estilo/base.css`, `web/estilo/componentes.css`, `web/tarefas.css`, `web/conteudo.css`, `web/mapa.css`,
`web/estilo/pagina_estilo.css`) e todo módulo JS usam `var(--i-*)`. A varredura `tests/unit/test_estilo_tokens.py`
reprova literal de cor (hex, rgb/rgba/hsl, nome de cor) em css/js fora dos tokens e literal de medida em
`font-size`, `padding`, `margin`, `gap`, `border-radius` e `box-shadow`. Exceções declaradas: o valor de
`@media` (o CSS não aceita `var()` em consulta de mídia; os três cortes estão nos tokens e repetidos à mão) e
`web/favicon.svg` (imagem, não folha de estilo).

| grupo | tokens | regra |
|---|---|---|
| cor | `--i-fundo`, `--i-superficie`, `--i-superficie-2`, `--i-linha`, `--i-linha-forte`, `--i-texto`, `--i-texto-fraco`, `--i-acento`, `--i-acento-texto`, `--i-sucesso`, `--i-aviso`, `--i-erro`, `--i-sobre-estado`, `--i-veu` | um valor por tema; todo par texto × superfície >= 4,5:1 |
| cor derivada | `--i-acento-fraco/-medio`, `--i-sucesso-fraco`, `--i-aviso-fraco`, `--i-erro-fraco` (`color-mix` com transparência) | seleção, faixa, realce; funcionam nos dois temas |
| cartografia | `--i-carta-*` | fixa: um mapa não muda de paleta com o sistema; o painel sobre o canvas usa estas, nunca as do tema |
| tipografia | `--i-fonte-titulo/-texto/-dado`, escala `--i-t-1 .. --i-t6` (razão 1,125 sobre 14 px), pesos, entrelinhas | seção 3 |
| espaçamento | `--i-e0 .. --i-e8` = passo de 4 px × `--i-densidade` | densidade compacta 0,75 · normal 1 · confortável 1,25 |
| forma | `--i-raio` 2 px, `--i-raio-pilula`, `--i-fio` 1 px, `--i-fio-forte`, `--i-fio-marca` 3 px, `--i-foco-largura` 2 px, `--i-tique`, `--i-regua-passo`, `--i-sombra`, `--i-tempo` | cantos retos; foco sempre visível em âmbar |
| leiaute | `--i-largura-*`, `--i-mini-*`, `--i-corte-*` | larguras de barra, diálogo, colunas, miniaturas |
| compatibilidade | `--fundo`, `--painel`, `--acento`, `--e1..e6` etc. | apontam para os `--i-*`; só `var()`, nunca valor |

Tema em três estados (regra da casa): "sistema" (sem atributo, `prefers-color-scheme` decide), `html[data-theme=
"light"]`, `html[data-theme="dark"]`. Densidade em três: `html[data-densidade="compacta|confortavel"]` (normal =
sem atributo). Os dois são escolhidos na barra lateral (tema) e em `/estilo` (tema e densidade), guardados em
`localStorage` (`plat_tema`, `plat_densidade`) e aplicados antes da primeira pintura por `web/js/base/tema.js`
(script clássico no `<head>` de toda tela).

## 3. Tipografia: par com motivo

| papel | família | pesos | por quê |
|---|---|---|---|
| exibição | Big Shoulders Display | 700, 800 | condensada e industrial, letra de placa de instrumento; dá carácter à marca, ao h1/h2 e ao cabeçalho de tabela sem ocupar largura. Nunca em parágrafo: condensada demais para corrida |
| texto | IBM Plex Sans | 400, 500, 600 | humanista-neutra, legível em texto longo e em formulário; o contraste com a exibição é deliberado — a mesma fonte para tudo é o painel genérico que o dono rejeitou |
| dado | IBM Plex Mono | 400, 500 | algarismos de largura fixa (`font-variant-numeric: tabular-nums` ligado em `body`), para número alinhar em coluna como num mostrador digital; tabela, coordenada, código, id, régua |

Vendorizadas em `web/vendor/` (subconjunto latin, fonte variável quando o Google Fonts a serve assim), sha256 e
origem em `web/vendor/VERSOES.txt`, licença OFL-1.1 conferida arquivo a arquivo no repositório `google/fonts`;
`tests/unit/test_vendor.py` confere o hash. Sem CDN em nenhuma tela.

## 4. Ícones: uma família só

`web/js/base/icones.js`: desenhados por DOM em SVG, caixa 24 × 24, traço 1,6, pontas e junções redondas, cor
corrente, `aria-hidden` (o rótulo vai ao lado; ícone sozinho num botão exige `aria-label`). A lista cobre tipos
de item do catálogo, navegação, ações, estados (ok, erro, atenção, info, carregando, pendente, rodando,
concluído, falhou, cancelado, vazio, desconhecido), tema, densidade e régua. Nenhum emoji e nenhum glifo de
texto (✓ ✗ ○ ● ⋯ ▾ ▸ ↑ ↓ ×) no produto: a varredura de `tests/unit/test_estilo_tokens.py` reprova qualquer
carácter fora do bloco tipográfico admitido (travessão, reticências, ponto mediano, aspas, sinais de grau).

## 5. Componentes de base e os sete estados

Os seis componentes (`<plat-aviso>`, `<plat-busca>`, `<plat-dialogo>`, `<plat-formulario>`, `<plat-paginacao>`,
`<plat-tabela>`, em `web/js/base/componentes/`) têm os sete estados desenhados em `web/estilo/componentes.css`
e demonstrados com os elementos reais em `/estilo`:

| estado | como se vê |
|---|---|
| repouso | superfície-2 sobre superfície, fio de 1 px em `--i-linha-forte` |
| foco visível | contorno de 2 px em âmbar com recuo de 2 px (`:focus-visible`), em todo elemento interativo, inclusive linha de tabela e aviso de erro |
| ativo | fundo `--i-acento-medio` (botão pressionado), `aria-selected` com faixa âmbar à esquerda (linha de tabela), `aria-pressed` preenchido (vistas, tema) |
| desativado | opacidade 0,5, cursor `not-allowed`, fio em `--i-linha`; `plat-tabela[disabled]` e `plat-busca[disabled]` desativam os controles internos |
| carregando | `aria-busy="true"`: giro em âmbar (`plat-gira`) no botão, no aviso, na busca e na paginação; linhas-esqueleto pulsando na tabela; corpo esmaecido no diálogo |
| vazio | desenho com o ícone `vazio` e texto ("nenhum item", "formulário sem campos", "nada a mostrar"); aviso vazio some |
| erro | cor `--i-erro` com ícone `erro`, `role="alert"`, foco no aviso; campo com `aria-invalid` e faixa vermelha; tabela com linha de erro e botão "tentar de novo" |

## 6. Como medir (e o que ainda não foi medido)

- `tests/unit/test_estilo_tokens.py`: literal de cor/medida fora dos tokens, glifo/emoji, ícone fora da família,
  fontes no vendor com sha, toda tela ligando as três folhas e o `tema.js`, rota `/estilo` registrada.
- `tests/e2e/test_estilo.py` (marcador `lento`, chromium do playwright): captura antes/depois das telas em
  `tests/e2e/capturas/L0-14_<tela>_{antes,depois_escuro,depois_claro}.png`; contraste de todo nó de texto
  visível nas telas, nos dois temas, com a fórmula WCAG 2 aplicada à cor calculada e ao fundo composto
  (`axe-core` roda por cima quando existe no disco, fora do repositório); página `/estilo` com o número de
  tokens igual ao do arquivo; os 6 × 7 estados presentes.
- Resultados em `tests/medidas/L0-14.json`, cada um com o comando.
