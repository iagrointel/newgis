---
id: construtor
titulo: Construtor de aplicativos
titulo_en: App builder
titulo_es: Constructor de aplicaciones
resumo: "montar um aplicativo por arrasto: páginas, grade, mapa e painéis, sem escrever código"
resumo_en: "build an app by drag and drop: pages, grid, map and panels, without writing code"
resumo_es: "montar una aplicación arrastrando: páginas, cuadrícula, mapa y paneles, sin escribir código"
classe: tela
pagina: construtor.html
caminho: /construtor
e2e: tests/e2e/test_layout_paginas.py
captura: L0-02-tenant-auth_construtor_paginas.png
e2e_captura: capturar("construtor_paginas")
palavras: [construtor, aplicativo, app, arrastar, paginas, grade, mapa, painel, layout]
palavras_en: [builder, app, drag, drop, pages, grid, map, panel, layout]
palavras_es: [constructor, aplicacion, arrastrar, paginas, cuadricula, mapa, panel, diseño]
---

## Construtor de aplicativos

O construtor monta um aplicativo do inquilino por arrasto: páginas, linhas e colunas, mapa central,
painéis laterais e janelas. O resultado é um item do catálogo (tipo aplicativo) que abre no
executor.

1. Abra o construtor pela lista de Conteúdo (novo aplicativo) ou por `/construtor?item=<id>`.
2. Arraste um componente da paleta para a árvore de páginas: a soltura na posição certa cria a
   linha e a coluna.
3. O painel de propriedades edita título, proporção e conteúdo de cada nó.
4. Salvar grava a estrutura; o executor (`/executar`) mostra o aplicativo ao usuário final.

A estrutura nasce de arrasto de verdade (HTML5 Drag and Drop), não de formulário: o que o teste de
ponta a ponta prova é o mesmo gesto do usuário.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_layout_paginas.py`) contra a versão atual.
