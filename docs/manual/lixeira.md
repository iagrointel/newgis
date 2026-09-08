---
id: lixeira
titulo: Lixeira
titulo_en: Trash
titulo_es: Papelera
resumo: "itens apagados ficam aqui por 30 dias; restaurar ou expurgar de verdade"
resumo_en: "deleted items stay here for 30 days; restore or purge for good"
resumo_es: "los ítems borrados quedan aquí por 30 días; restaurar o expulsar de verdad"
classe: tela
pagina: conteudo_lixeira.html
caminho: /conteudo/lixeira
e2e: tests/e2e/test_conteudo.py
captura: L0-03_lixeira.png
e2e_captura: capturar("lixeira")
palavras: [lixeira, apagar, restaurar, expurgar, 30 dias, trash]
palavras_en: [trash, delete, restore, purge, 30 days]
palavras_es: [papelera, borrar, restaurar, expulsar, 30 dias]
---

## Lixeira

Apagar um item manda para a lixeira: o item sai do catálogo e das buscas, mas continua no
inquilino por 30 dias.

1. Abra a lixeira pelo menu de Conteúdo.
2. Restaurar devolve o item à pasta de origem com as permissões que tinha.
3. Expurgar remove de verdade (com a tabela física, em itens de camada); a ação pede confirmação.

Passados 30 dias, o expurgo é automático.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_conteudo.py`) contra a versão atual.
