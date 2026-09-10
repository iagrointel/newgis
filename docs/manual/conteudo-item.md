---
id: conteudo-item
titulo: Detalhe do item
titulo_en: Item detail
titulo_es: Detalle del ítem
resumo: "ficha do item: atributos, metadado, permissões, histórico e ações"
resumo_en: "item card: attributes, metadata, permissions, history and actions"
resumo_es: "ficha del ítem: atributos, metadato, permisos, historial y acciones"
classe: tela
pagina: conteudo_item.html
caminho: /conteudo/{id}
e2e: tests/e2e/test_conteudo.py
captura: L0-03_detalhe.png
e2e_captura: capturar("detalhe")
palavras: [detalhe, item, atributos, metadado, permissões, historico, editar, apagar]
palavras_en: [detail, item, attributes, metadata, permissions, history, edit, delete]
palavras_es: [detalle, item, atributos, metadato, permisos, historial, editar, borrar]
---

## Detalhe do item

Cada item tem uma ficha: nome, descrição, categoria, pastas, atributos próprios, metadado
(descricao), permissões e histórico de mudanças.

1. Abra um item a partir da lista de Conteúdo.
2. A ficha mostra o que o item é: camada carregada, documento, conexão ou referência.
3. Editar abre o painel de atributos; apagar manda para a lixeira (restaurável por 30 dias).
4. Em itens de camada, a ficha aponta a pré-visualização no mapa e a exportação do metadado ISO.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_conteudo.py`) contra a versão atual.
