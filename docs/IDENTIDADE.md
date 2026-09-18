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

- `make tokens` é o portão inteiro em um comando: `tests/unit/test_tokens_cor.py` (a varredura de cor, a única
  do repositório — css, css dentro de html e js, com controle positivo que planta um literal e confere que a
  varredura o pega), `tests/unit/test_telas_carregam_tokens.py` (toda tela carrega `tokens.css` antes de
  qualquer outra folha), `tests/unit/test_estilo_tokens.py` (grupos de token, par tipográfico com sha256,
  família única de ícones sem emoji, os 6 componentes nos 7 estados, rota `/estilo` gerada dos tokens) e
  `tests/unit/test_tokens_visuais.py` (medida de escala).
- Cor no JavaScript: existe código que NÃO resolve `var(--...)` por construção — o estilo do MapLibre é JSON
  lido pelo canvas, a cena 3D é configuração de renderização, alguns gráficos são SVG montado em memória e
  exportado fora do documento. Ali a cor é cartografia ou dado, nunca cromo. Esses arquivos não ficam
  "liberados": cada um tem ORÇAMENTO CONTADO em `tests/tokens_cor.excecoes` (`caminho @N  # motivo`), e tanto
  crescer quanto encolher sem atualizar o número reprova. CSS não tem orçamento: é zero absoluto.
- `tests/e2e/test_estilo.py` (marcador `lento`, chromium do playwright): captura antes/depois das telas em
  `tests/e2e/capturas/L0-14_<tela>_{antes,depois_escuro,depois_claro}.png`; contraste de todo nó de texto
  visível nas telas, nos dois temas, com a fórmula WCAG 2 aplicada à cor calculada e ao fundo composto
  (`axe-core` roda por cima quando existe no disco, fora do repositório); página `/estilo` com o número de
  tokens igual ao do arquivo; os 6 × 7 estados presentes.
- Resultados em `tests/medidas/L0-14-identidade-visual.json`, cada um com o comando.
- Cláusulas (f) e (g) PROVADAS com o chromium do **playwright** (`~/.cache/ms-playwright`): o que quebra nesta
  máquina é o `google-chrome` do sistema, não ele. Regenerar a prova inteira:
  `bash tests/e2e/regerar_capturas_L0-14.sh` — sobe as duas instâncias do par antes/depois contra o mesmo banco,
  mede o contraste nos dois temas, roda o axe e grava as capturas. Os PNG não entram no git; o que fica
  versionado é o script e o inventário com sha256 em `tests/e2e/capturas/INVENTARIO_L0-14.txt`.
- O axe entra por URL do mesmo domínio, servida por interceptação de rota do playwright: a CSP do produto
  (`script-src 'self' 'nonce-...'`) recusa script inline, e não se afrouxa CSP para caber ferramenta de teste.
- O que ainda NÃO foi medido, e por quê: A migração das telas da folha antiga
  `web/style.css` para `estilo/base.css` + `estilo/componentes.css` é item próprio; enquanto ela não acontece,
  o número de telas na folha antiga está sob catraca (`TELAS_NA_FOLHA_ANTIGA` em
  `tests/unit/test_estilo_tokens.py`): não pode crescer, e tela nova nasce na folha nova.

## 7. Migração da folha antiga, tela a tela (item L0-14-b)

O item L0-14 deixou o sistema de design de pé e a catraca `TELAS_NA_FOLHA_ANTIGA` marcando quantas telas
ainda carregam `web/style.css` em vez de `estilo/base.css` + `estilo/componentes.css`. Este item desce essa
catraca. A regra é uma só: **troca de folha, não redesenho**. Desenho é decisão do dono; aqui só se troca a
folha que a tela carrega, e prova-se que a tela continua a mesma.

Como uma leva é migrada e provada:

1. a ordem é de RISCO, escrita em `tests/e2e/telas_migracao.json`: tela sem folha própria antes de tela com
   folha própria, mapa/SIG/construtor por último, e por tamanho dentro de cada grupo. Leva = 8 telas;
2. `bash tests/e2e/regerar_capturas_migracao.sh <leva>` sobe DUAS instâncias contra o MESMO banco de trilha
   (`plat_ttelas`, nunca o schema `plat` de produção): o "antes" é o HEAD anterior à leva, servido de uma
   worktree própria, e o "depois" é a árvore de trabalho. A única diferença entre as fotos é a folha;
3. `tests/e2e/test_migracao_folha.py` roda as duas fases: fotografa cada tela nos dois temas, grava a
   IMPRESSÃO DIGITAL DA ÁRVORE (tag, id e classes de cada elemento, em ordem de documento), mede o contraste
   de todo nó de texto visível com a fórmula do L0-14 e roda o axe-core;
4. `tests/e2e/compara_migracao.py` dá o veredito da leva. Reprova se a árvore mudou, se a tela montava e
   deixou de montar, ou se apareceu violação de contraste ou de axe que não existia antes. Violação que já
   existia na folha antiga fica registrada como HERDADA: não é regressão desta migração, e não se conserta
   aqui — consertar seria redesenhar;
5. `tests/e2e/grava_medida_migracao.py` escreve `tests/medidas/L0-14-b-migracao-folha.json` a partir dos
   vereditos. Nenhum número é digitado.

O que a fase "antes" mede e que decide a migração: os seletores de `web/style.css` que de fato PEGAM naquela
tela (`document.querySelector` de cada um, no navegador) e, desses, os que a folha nova não cobre
(`so_na_antiga_e_pegam`). Regra de corte: regra de LAYOUT que só existe na folha antiga é levada para a folha
nova, verbatim; regra puramente cosmética cuja equivalente já existe na folha nova é descartada, e a diferença
aparece no par de capturas. Tela que não passa sem redesenho PARA: fica com `estado: deixada_para_tras` e o
motivo escrito no manifesto.

Armadilhas desta máquina: o chromium é o do PLAYWRIGHT (o `google-chrome` do sistema quebra), e **nunca se
contém memória com `ulimit -v`** — endereçamento virtual não é memória e o Chromium morre com SIGTRAP sob esse
teto; o teto vai em `systemd-run --scope -p MemoryMax=`.
