# Tabela de atributos: a contagem é sob pedido, e a vista é do usuário

Data: setembro de 2026 · Item: L2-01-g-tabela-atributos · Estado: aceita

## Contexto

A tabela de atributos pagina no servidor. O portão do item pede duas coisas que puxam em sentidos opostos:
a contagem exibida tem de bater com `COUNT(*)` sob o mesmo filtro, e a primeira página de uma camada de
1 milhão de linhas tem de sair em 300 ms no percentil 95.

Medido nesta base, numa camada de 1.000.000 de feições com geometria (721 MB com a tabela e os índices):

- a página em si, pelo índice, sai em 15,2 ms no percentil 95 (20 repetições);
- o `COUNT(*)` sob o mesmo filtro sai em 263 ms, sozinho, porque a política de segurança por linha vira
  `current_setting('plat.tenant_id', true)`, que é `PARALLEL RESTRICTED`: a varredura é serial, sem os
  quatro processos auxiliares que o mesmo `COUNT(*)` usa quando a tabela não tem política.

Ou seja, numa camada grande a contagem custa mais de dez vezes a página que ela acompanha.

## Decisão

1. `POST .../linhas` aceita `contar` (padrão verdadeiro). Com `contar: false` a resposta traz `total: null`
   e `paginas: null`. A tela conta uma vez, quando o FILTRO muda (busca, extensão, seleção, camada), e não
   reconta ao trocar de página nem ao reordenar — nem uma nem outra muda quantas linhas passam pelo filtro.
2. A vista da tabela (ordem das colunas, rótulo, oculta, largura, domínio) fica em `plat.tabela_vista`,
   uma linha por (item, usuário), com política por inquilino e por usuário. Não fica no navegador: o
   portão pede que a largura volte depois de recarregar, e `localStorage` não atravessa máquina nem sessão.
3. Coluna oculta não sai da API de colunas — nem o nome, nem o valor na linha. Quem precisa desfazer lê
   `GET .../vista`, que devolve a vista inteira, inclusive o que está escondido.

## Consequências

- Quem chama a API sem se importar com o custo não muda nada: sem o campo, a contagem vem.
- A contagem exibida continua sendo `COUNT(*)` de verdade sob o mesmo filtro, na mesma transação da
  página — nunca uma estimativa de `reltuples`.
- Ordenar por coluna sem índice continua sendo uma varredura com ordenação: a API não promete o que o
  banco não tem. Criar índice por coluna de atributo é decisão do administrador da camada, e o índice
  precisa existir ANTES de `plat.camada_preparar()` — medido nesta base, um índice criado depois da
  reescrita que a função faz não foi escolhido pelo planejador.

## Alternativas descartadas

- **Estimativa de `reltuples`**: barata, mas o portão pede que o número bata com `COUNT(*)`, e uma
  estimativa erra em tabela recém-carregada, que é justamente o caso de uma camada nova.
- **Cache do total no servidor**: guardaria um número por combinação de filtro, com invalidação a cada
  edição da camada. Complexidade sem pedido; a tela já sabe quando o filtro mudou.
