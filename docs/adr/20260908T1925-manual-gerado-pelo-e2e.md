# Manual gerado pelo e2e, com ajuda por contexto (item L7-04-a-manual-capturas-geradas)

Data: 08/09/2026. Estado: aceito. Par: `laco/decomposicao/L7_CONCEITO.md`; ADR `20260907T1355-paginas-e-layout-do-app.md` (o layout é quem instala o botão de ajuda).

## Contexto

O manual escrito à mão apodrece: a tela muda, o texto fica, e a captura colada mostra uma versão que
não existe mais. O item pede o contrário: manual GERADO, com uma seção por tela, cada seção com a
captura que o TESTE de ponta a ponta da própria tela produziu contra a versão atual, captura
desatualizada reprovando o build, e ajuda por contexto dentro do app (botão que abre a seção da tela,
com busca, nos 3 idiomas).

## Decisão

1. **Uma fonte só, em Markdown com front matter** (`docs/manual/<tela>.md`): `id`, títulos e resumos
   em pt-BR/en/es, `e2e` (arquivo do teste), `e2e_captura` (trecho literal que o teste usa para gravar
   a imagem — `capturar("lista")` ou `"{ITEM}_lista.png"`), `captura` (nome final do arquivo em
   `tests/e2e/capturas/`), palavras-chave nos 3 idiomas, corpo. Nada aqui roda pytest: quem regenera
   captura é o e2e da tela; `docs/gerar_manual.py` só valida, copia e monta.
2. **Captura versionada por VERSÃO, não por commit**: `tests/e2e/capturas/<tela>@<versao>.png` é uma
   cópia nomeada da captura base, feita no build. Versão de captura diferente da versão do app REPROVA
   (`make manual` sai com erro pedindo regeneração). Por sha ficou impraticável: toda mudança de
   código pederia captura nova, inclusive mudança que não toca a tela.
3. **`web/dados/manual.json` é GERADO e COMMITADO** (diferente do site e do PDF, que ficam fora do
   git): o painel de ajuda do app consome `/static/dados/manual.json` e precisa funcionar também
   quando o build do manual não rodou naquela máquina. Um teste de unidade regenera o JSON e reprova
   se o commitado divergir.
4. **Painel de ajuda é um módulo do layout** (`web/js/base/ajuda.js`, instalado por `montarLayout`):
   toda tela declara `data-ajuda="<chave>"` no `<body>`; o painel abre na seção da tela (destaque no
   item atual), tem busca (E lógico de termos, sem diacrítico, pontos título 4 > palavras 3 > resumo 2
   > corpo 1), seletor de idioma e fecha com Esc. HTML do corpo entra pela única porta da casa
   (`htmlSeguro`/DOMPurify). A MESMA função de busca fica em `window.platAjuda.buscar` — o e2e mede o
   caminho que a interface usa, não uma cópia.
5. **PDF por weasyprint do `~/.local`, chamado por SUBPROCESSO**: a venv não tem produtor de PDF e o
   `make` exporta `PYTHONNOUSERSITE=1`, que esconde o módulo — o gerador tira a variável do ambiente
   do filho. Os 3 idiomas existem no manual inteiro (título/resumo/palavras); o CORPO traduzido
   completo é o item L7-10-a (no painel, corpo em en/es mostra o resumo traduzido e aponta o manual).

## Consequências

- `make manual` (valida → roda os 14 e2e pelo semáforo → monta HTML+PDF+JSON) é o portão: captura de
  tela que não existir mais reprova. Rota `/manual` serve o HTML com `noindex`.
- Em trilha (worktree), o e2e precisa do nginx TLS da frente (`/static` é do nginx) — receita no
  handoff T8, certificado autoassinado aceito via `ignore_https_errors` no conftest de e2e (sem efeito
  com certificado de verdade) e `SSL_CERT_FILE`/`NODE_EXTRA_CA_CERTS` no httpx e no driver Node.
- `L5-01-a-layout-paginas` (construtor) já estava mergeado: o e2e do construtor cria o item `app` pela
  API e produz a captura — nenhuma pendência deste item para ele.
