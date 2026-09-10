# Linha de comando `plat`: um ponto de entrada só, falando com a própria API

Item L0-14-cli-admin. Estado: aceito.

## Contexto

Três ramos criaram, no mesmo dia e sem se falar, três `scripts/plat` diferentes: um atalho de `sh` para
`scripts/plat.py` (L7-06-c), um utilitário `argparse` com o grupo `demo` (L7-01-c) e um atalho de `bash`
para `python -m app.cli` que carregava `PLAT_DSN_WORKER` do cofre (L7-33). Em `master` havia ainda um
quarto, de `bash`, que só sabia `segredo rotacionar` (L7-19). Todos com o mesmo nome de arquivo: o
primeiro a ser juntado ganharia e os outros virariam conflito.

A instalação, o laço agêntico da operação e quem instala em casa precisam do mesmo conjunto de verbos —
inquilino, usuário, token, camada, job, evento — e nenhum deles pode depender de alguém abrir o navegador.

## Decisão

1. **Um executável só**: `scripts/plat`, vinculado em `venv/bin/plat` pelo `install.sh`. Ele não decide
   nada: escolhe o Python da venv e chama `python -m app.cli`. O código dos comandos vive em `app/cli/`.
2. **A CLI é um cliente da API, não um segundo caminho para o banco.** Cada subcomando faz login com uma
   credencial de arquivo e chama exatamente as rotas que a tela chama. Consequência que justifica a
   escolha: privilégio, RLS, cota, limite de corpo e **evento de auditoria** são os mesmos, sem nenhuma
   linha duplicada — e o teste do item consegue comparar o efeito da CLI com o da rota, um a um.
   O preço é depender da API no ar; para a semeadura da instalação isso é aceitável porque a etapa `k`
   vem depois da etapa `h`, que sobe o serviço.
3. **Senha nunca por argumento.** `--senha` e parentes são recusados antes de qualquer chamada, com a
   instrução do caminho certo: `--senha-stdin` ou `--senha-arquivo` (arquivo em modo 600, conferido).
   Isto fecha o achado 6a do adversário do T1 (senha no `COMMAND=` que o `sudo` grava no journal) e vale
   também para os arquivos de credencial e de segundo fator.
4. **Zero dependência nova**: `argparse`, `urllib`, `http.cookiejar`, `csv` e `json`. `app.auth.totp` é
   importado tarde, só quando o login exige segundo fator.
5. **`docs/CLI.md` é gerado do `argparse`** (`plat docs`), e o teste reprova se estiver velho: comando sem
   documentação passa a ser impossível por construção, como já acontece com `docs/LIMITES.md`.
6. **A ajuda é em português**: `argparse` fala inglês, e em vez de catálogo `gettext` (dependência e
   arquivo binário no repositório) o texto formatado passa por uma tabela pequena e fechada de
   substituições, coberta por teste que varre os 28 parsers procurando resto de inglês.

## O que ficou de fora, e por quê

`backup agora/verificar/restaurar-drill` e `item exportar/importar pacote` estão na hipótese do item, mas
`app/backup` e o pacote do inquilino ainda não estão em `master` (ramos `wt/il006adumpl`, `wt/il006cresto`
e `wt/il006dexpor` na fila de junção). A regra do item é que a CLI **chama** o que existe e nunca duplica;
como não existe nesta árvore, o subcomando não foi inventado. Quando esses ramos entrarem, cada um
acrescenta o seu grupo em `app/cli/principal.py` e regenera `docs/CLI.md` — sem tocar em mais nada.

`plat camada importar` exige `--formato` em vez de deduzir pela extensão: a rota que publica a tabela de
formatos (`GET /api/importacoes/formatos`) hoje é encoberta por `GET /api/importacoes/{id}`, declarada
antes dela, e responde 404 `importacao_inexistente`. Deduzir a extensão por uma tabela local repetiria o
que é da API. O conserto é de `app/ingestao/rotas.py` (item L0-04) e está anotado no repasse.
