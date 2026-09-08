# ADR — telas de operação: fila de envio por byte, página pública sem chrome, formulário de conexão (UX-05)

Data: setembro de 2026. Estado: aceito. Trilha de interface.

## Contexto
Quatro telas de operação chegaram ao alfa com buracos: `/conexoes` lia a API mas não criava, editava nem apagava
(POST/GET/PATCH/DELETE de `/api/conexoes` sem controle — UX-13); `/uploads` enviava um arquivo por vez com progresso
por PARTE de 16 MiB (num arquivo de 2 GB a barra dava 128 saltos e ficava parada 16 MiB de cada vez) e sem fila;
`/tarefas` tinha todo o texto em português cravado no código; `/c/<token>` montava a barra lateral do produto numa
página anônima e não mostrava a ficha dos itens incluídos (`GET /api/compartilhado/{token}/itens/{id}` sem tela).

## Decisão
1. **Progresso por byte, não por parte.** O envio de cada parte passa a `XMLHttpRequest` (o único caminho do
   navegador que expõe `upload.onprogress`; `fetch` não expõe o progresso de envio). Cada parte continua sendo um
   `Blob.slice` do arquivo — nada é lido inteiro para a memória — e a tela pinta no máximo uma vez por quadro
   (`requestAnimationFrame`), com bytes enviados, velocidade e tempo restante. É isso que sustenta a refutação
   "upload de 2 GB mostra progresso sem travar a tela": o custo por quadro não cresce com o tamanho do arquivo.
   O e2e mede as tarefas longas do fio principal (`PerformanceObserver longtask`) num arquivo sintético de 256 MiB
   com as rotas de parte e conclusão interceptadas no navegador (o disco dos servidores está a 94–96 %; um arquivo
   real de 2 GB não cabe no orçamento do laço, D21). O caminho real continua provado pelos 100 MiB de
   `tests/e2e/test_uploads.py`.
2. **Fila de arquivos.** `<input multiple>` e arrastar vários; uma linha por arquivo com barra própria, estado
   (na fila, enviando, concluindo, concluído, falhou, cancelado), cancelar por arquivo ou tudo, tentar de novo e
   remover. Um arquivo por vez na rede (as partes já são sequenciais; paralelizar arquivos só disputa a mesma
   banda) — a fila é ordem, não concorrência. Todo erro da API aparece nomeado na linha do arquivo (413 de cota,
   415 de tipo, rede caída na parte N), nunca um status cru. A tela expõe `window.plat.uploads.fila()` só para a
   suíte medir.
3. **Conexão criada, editada e apagada pela tela**, com `<plat-formulario>`: nome, tipo (travado depois de
   criada — o protocolo define o leitor; trocar é criar outra), endereço, modo, config JSON e credencial. A
   credencial nunca volta do servidor; o formulário de edição só diz "há uma credencial guardada" e oferece
   trocar ou remover. Os três 422 do servidor (`url_insegura`, `config_grande_demais`, lista do pydantic) e o 409
   de nome vão para o CAMPO certo, com foco. Apagar pede confirmação e diz o que fica (as camadas já publicadas).
   A lista ordena por coluna no cliente (é pequena: dezenas por inquilino) e busca por nome, tipo, modo e URL.
4. **Página pública sem chrome interno.** `/c/<token>` deixa de usar `.app` + `#lateral`: cabeçalho próprio
   (marca, idioma, tema), conteúdo e rodapé que diz o que a página é. Não há sessão a mostrar nem menu a que ir; a
   barra lateral ali era um convite a URLs que devolvem 401. Os quatro estados do link (carregando, inválido 404,
   expirado 410, muitos pedidos 429, erro) são um `<plat-estado>` nomeado. "Ver" num item incluído abre a ficha
   dele pela rota do item, no mesmo contexto do link.
5. **Estados explícitos em todas as quatro telas** pelo `<plat-estado>` do sistema de design (UX-01): lista de
   conexões (vazio com "nova conexão", carregando, erro com referência e tentar de novo, negado), lista de tarefas
   (vazio com "limpar filtros" quando há filtro, erro, negado), detalhe de tarefa (id inexistente com "fechar"),
   agendas (erro) e tipos de upload (erro com tentar de novo). Nenhuma linha "vazia" dentro de `<tbody>`.
6. **Texto só pelo dicionário.** `jobs/formato.js` passa a importar `t()` e `idiomaAtual()` (número, "hoje",
   "ontem", estados); as três telas aplicam `data-i18n` no HTML e `aoTraduzir` nas partes montadas em JS. pt-BR
   mantém as frases anteriores letra a letra (os e2e de L0-05 e L6-02 seguem valendo); en e es com paridade.

## Consequências
- Um e2e que intercepta `PUT partes` prova mecanismo, não a rede real: a medida em `tests/medidas/UX-05.json` é
  do fio principal do navegador, não do tempo de envio.
- `jobs/formato.js` deixa de ser "puro sem dependência": quem o usar fora de uma página com `carregar()` do i18n
  recebe a chave em vez do texto (o dicionário padrão é pt-BR e é carregado por toda tela).
- A página pública tem `plat-tema` e `plat-idioma`, logo depende de `componentes.js`; segue sem `layout.js`
  além de `pronto()`.

## Alternativas recusadas
- `fetch` com `ReadableStream` no corpo para ter progresso de envio: exige HTTP/2 e cabeçalho `duplex`, não passa
  pelo proxy da trilha e ainda não expõe bytes confirmados pelo servidor. XHR faz isso há vinte anos.
- Uma tabela genérica `<plat-tabela>` para a lista de tarefas: as linhas mudam uma a uma por SSE e o cabeçalho
  ordena no servidor; a tabela própria continua (decisão do L0-05), só ganhou o estado explícito.
- Esconder a barra lateral com CSS na página pública: o HTML continuaria pedindo `/api/eu` e montando menu; a
  decisão é não ter o chrome, não ocultá-lo.
