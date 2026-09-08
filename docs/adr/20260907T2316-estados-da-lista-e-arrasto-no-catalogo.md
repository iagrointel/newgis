# ADR — catálogo: estados explícitos, arrasto de arquivo pelo caminho único de upload, seleção por id (UX-03)

Data: setembro de 2026. Estado: aceito. Trilha de interface.

## Decisão
1. Toda área de lista mostra um `<plat-estado>` nomeado (vazio/carregando/erro/negado) dentro da própria área
   (`#lista`), para a área nunca ficar sem altura nem sumir; o estado vazio distingue "sem itens" de "sem resultado
   para a busca/pasta/filtro" (`data-filtrado`) e oferece a ação certa em cada caso.
2. Arrastar e soltar arquivos sobre a lista usa o MESMO caminho do diálogo "Novo item > Arquivo"
   (`novo.js::enviarArquivoComoItem`): upload retomável por partes com token de serviço em memória, conferência de tipo
   no servidor, item criado ao concluir. Alternativa sem arrasto continua sendo o diálogo (WCAG 2.5.7).
3. A seleção em massa é por id e sobrevive a reordenar, filtrar e "carregar mais"; zera só por troca de aba ou
   "limpar seleção" (refutação do item).
4. `lista.js` deixa `performance.measure('catalogo:render')` a cada render; é a régua do p95 e fica em produção
   (custo desprezível, medível por qualquer um no DevTools).

## Achado para o dono da rota de upload (L0-04-a)
As rotas de partes/conclusão/aborto só aceitam token com escopo `admin:inquilino` (medido em UX-03); um editor com
`conteudo.criar` não consegue enviar arquivo pelo navegador. A interface mostra a mensagem da API; a correção do
escopo é do backend.
