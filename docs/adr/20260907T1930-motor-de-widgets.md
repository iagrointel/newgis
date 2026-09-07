# ADR 20260907T1930 — motor de widgets: falha por módulo, chrome de edição por atributo, texto inerte

Item L5-06-motor-widgets. Segue L5_CONCEITO D1 (sem framework), D5 (barramento EventTarget com corte
de recursão), D19 (manifesto por widget, `import()` só dos citados) e D23 (sanitização).

## Decisões

1. **Falha de módulo é local ao tipo.** `montarWidgets` carrega cada módulo citado em `try`; o que não
   carrega (arquivo apagado, 404, sintaxe) entra em `falhas` e cada nó daquele tipo vira caixa de erro
   nomeada (`role=alert`, `data-widget=<tipo>`). Os outros widgets montam e as ligações seguem valendo.
   A página `/aplicativo` marca `data-pronto` mesmo quando o motor inteiro falha, com a mensagem no
   `<main>`: nunca tela em branco.
2. **Chrome de edição = atributo + CSS, não segundo renderizador.** `motor.edicao(true|false)` alterna
   `data-edicao` na grade e `tabindex`/`aria-label` nos widgets; `widgets.css` desenha contorno e
   rótulo com o tipo. A instância do widget é a mesma nos dois modos (o e2e confere identidade do
   elemento e do `<table>` interno). O construtor de arrasto (L5-01) pendura o seu comportamento nisto.
3. **Texto entra só por `textContent`.** O campo `texto` é texto puro e HTML nele fica inerte; o
   DOMPurify vendido (`web/js/base/dom.js:htmlSeguro`) só entra quando houver campo de texto rico
   (Markdown, D23), em item próprio. Tabela, legenda, botão e filtro também só usam `textContent`.
4. **`integer` no esquema aceita `number` inteiro** (JSON Schema; `typeof` não distingue os dois).
   Achado ao rodar o e2e: o texto de demonstração com `nivel: 1` era recusado pelo validador.

## Fora deste item
Página do construtor (arrasto, paleta, painel de propriedades), fontes de dado ligadas a vistas (D4),
texto rico, sandbox por iframe para widget de terceiro (D19).
