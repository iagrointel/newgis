# ADR — Narrativa determinística do resultado do motor AMC

Item: L3-20-narrativa-de-resultado · Trilha: wt/il320narrat · Turno: plataforma-48

## Decisão

O resumo textual do resultado (`app/amc/narrativa.py`) é um TEMPLATE puro sobre o documento canônico
`plat/amc_metodo`: `narrar(documento, top_n=3)` devolve um texto linha a linha (uma ideia por frase)
com o modelo, as top-N unidades por nota e as ressalvas do documento. Nenhum modelo de linguagem
participa. O módulo é puro: sem banco, sem arquivo, sem relógio — mesmo documento, mesmo texto.

Junto vem o revisor automático (`revisar(texto, documento)`), que implementa a refutação do item:
ele devolve a lista das frases marcadas por `numero_sem_origem` (número que não existe em lugar
nenhum do documento), `termo_proibido` (termo da lista da regra de escrita de 03/09) e
`pontuacao_proibida` (exclamação ou interrogação). O texto gerado pelo template passa com zero
marcações; frase fabricada por um adversário ("os pesos somam 17") é marcada.

## Por quê template e não modelo de linguagem

A hipótese do item pede "sem modelo de linguagem afirmando fato". Um LLM que escreve "a unidade X
tem nota 82 porque…" pode inventar o porquê; o template só emite frase cujo número veio de um campo
do documento, e cada explicação de magnitude é aritmética declarada (peso normalizado × valor do
fator de maior contribuição, com empate resolvido pela ordem dos fatores no modelo).

## A regra de número com universo

A regra de escrita de 03/09 pede número com universo, base e fonte. No texto a fonte é o próprio
documento (sha256 impresso e frase final "gerado por template a partir do documento") e o universo
aparece nas formas "X de 100" (escala) e "o resultado cobre Y unidades" (base). Contagem derivada
que não existe no documento (somatório de pesos, por exemplo) é justamente o que o revisor reprova.

## Varredura de números

`numeros_do_documento` varre valores, números DENTRO de textos (data, sha do motor, metades do
sha256) e DENTRO de chaves (o "256" de "sha256"). É a mesma regra do módulo do documento (item
L3-01-i); aqui ela vive na própria narrativa porque o módulo do documento ainda não está juntado à
master e o item tem de ser autossuficiente no merge. Quando o `app.amc.metodo` chegar, a função pode
ser reexportada de lá — os testes já fixam o comportamento.

## Deduplicação de frase

A conferência à mão do texto de 3 unidades achou a ressalva impressa duas vezes quando o documento
traz o mesmo texto em `aviso_pesos` e em `ressalvas`. O template salta frase idêntica já emitida
(comparação exata de cadeia, determinística).

## O que ficou fora

- Rota de API e integração com o PDF: o item é o texto. A página do relatório (L3-01-i) já traz as
  mesmas seções em forma de tabela; acoplar narrativa ao PDF é outro item.
- Escolha de idioma/tom parametrizável: o tom é o da regra de escrita de 03/09, fixo.
- Revisar texto de TERCEIROS contra o documento: o revisor serve para isso por construção (ele não
  presume que o texto veio daqui), e os testes cobrem o caso fabricado — mas o produto do item é o
  par narrar+revisar do nosso documento.

## Armadilha de teste registrada

O teste de fabricação usava "os pesos somam 8": o 8 existe no documento disfarçado dentro de
"2026-09-08" (varredura de números dentro de texto) e a marcação não saía. Trocado por 17. Isso é
comportamento correto do revisor (8 de fato existe no documento), e é a razão de a varredura incluir
textos — nenhum número impresso pode escapar da conta.
