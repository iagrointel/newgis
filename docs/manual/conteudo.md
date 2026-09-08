---
id: conteudo
titulo: Conteúdo
titulo_en: Content
titulo_es: Contenido
resumo: "catálogo do inquilino: pastas, itens, busca, filtro por categoria, favoritos e compartilhamento"
resumo_en: "tenant catalog: folders, items, search, category filter, favorites and sharing"
resumo_es: "catálogo del inquilino: carpetas, ítems, búsqueda, filtro por categoría, favoritos y compartición"
classe: tela
pagina: conteudo.html
caminho: /conteudo
e2e: tests/e2e/test_conteudo.py
captura: L0-03_lista.png
e2e_captura: capturar("lista")
palavras: [conteudo, catalogo, pastas, itens, busca, favoritos, compartilhar, grade, lista]
palavras_en: [content, catalog, folders, items, search, favorites, share, grid, list]
palavras_es: [contenido, catalogo, carpetas, items, busqueda, favoritos, compartir, cuadricula, lista]
---

## Conteúdo

A tela Conteúdo é o catálogo do inquilino: pastas e itens (camadas, documentos, conexões e
pacotes) em lista ou grade.

### Navegar e buscar

1. A coluna de pastas navega a hierarquia; o painel principal lista o conteúdo da pasta aberta.
2. A busca do topo filtra por nome e descrição; o filtro de categoria afina o resultado.
3. O seletor Lista / Grade muda a apresentação; a grade mostra miniatura quando o item tem.

### Favoritos e compartilhamento

A estrela de cada item marca favorito; a seção Favoritos concentra os seus. Compartilhar abre o
painel de permissão: por membro, por grupo ou por link com token (o link pode ter validade).

O catálogo respeita o inquilino: nenhum item de outro inquilino aparece, nem por busca nem por
link interno.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_conteudo.py`) contra a versão atual.
