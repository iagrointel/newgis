# ADR — mapa de cobertura da interface como portão (item UX-00)

Data: setembro de 2026. Estado: aceito. Trilha de interface (UX-00 a UX-09).

## Contexto

O produto vai a alfa privado com a regra "sem lacuna": toda rota da API e toda funcionalidade tem de ser alcançável
de uma tela, com controle e com estados vazio, carregando, erro e negado. Até aqui a cobertura era conferida de
cabeça; com 196 pares método × rota e 20 páginas, isso não escala nem se prova.

## Decisão

1. `docs/gerar_cobertura_ui.py` lê as rotas da aplicação viva (`app.main.app.openapi()`, a mesma fonte de
   `make openapi`), varre `web/` atrás dos literais de URL e do método do auxiliar que os usa, liga cada módulo às
   páginas que o carregam (grafo de `import` a partir de `app/paginas.py` e das rotas `include_in_schema=False`
   que chamam `paginas.servir`) e escreve `docs/COBERTURA_UI.md` (rota → tela/controle → estado) mais a linha de
   base `docs/cobertura_ui_lacunas.json` com as lacunas de ESCRITA conhecidas.
2. `tests/unit/test_cobertura_ui.py` reprova quando aparece uma rota de escrita sem tela fora da linha de base.
   A saída é dar controle na tela ou registrar a lacuna (`--registrar`), o que também cria o item `UX-<n>` no
   backlog do laço. A linha de base só encolhe conforme a trilha fecha itens.
3. Rotas para cliente externo (OGC API Records, GeocodeServer compatível com Esri, URL assinada, item público)
   ficam em `docs/cobertura_ui_excecoes.json`, uma por prefixo, sempre com motivo; contam como cobertas quando uma
   tela expõe a URL. Sem exposição, aparecem como `externo sem exposição`.
4. As heurísticas são de texto e estão declaradas no cabeçalho do gerador. O que elas não veem, o e2e de cada
   item vê. Só as lacunas de escrita reprovam; leitura sem tela e estado de erro ausente ficam visíveis no
   documento e nos itens UX.

## Consequências

- Quem acrescenta rota de escrita passa a acrescentar o controle na tela ou a registrar a lacuna no mesmo ramo.
- O documento é regenerado por `make cobertura-ui` na trilha (a fila regenera o OpenAPI, não este documento; a
  linha de base é o que o teste confere, por isso o documento pode ficar um passo atrás sem reprovar).
- A regra do prefixo ocorre por prefixo de caminho; uma rota nova sob um prefixo de exceção herda o motivo.
