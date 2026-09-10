# Exportador de subrede para OpenDSS

Data: setembro de 2026 · item `L4-05-a-exportar-opendss` · situação: aceito

## Contexto

A plataforma já sabe traçar e exportar uma subrede em JSON (item L4-04-b). Quem faz estudo elétrico não lê
JSON: lê OpenDSS. A casa já tinha um conversor de BDGD para OpenDSS, fora desta plataforma, e ele resolvia
13 códigos de tensão dos 110 do domínio da ANEEL — o código 63 (23,1 kV), que aparece num alimentador da
cooperativa de teste, ficava de fora e o modelo daquele alimentador saía errado em silêncio.

## Decisão

1. **A mesma rota, um formato a mais.** `GET .../subrede/{nome}/exportar?formato=dss` devolve um zip com a
   pasta `.dss`. Não nasce rota nova: o objeto exportado é o mesmo, muda a representação. `formato=json`
   continua sendo o padrão.
2. **Correspondência declarada e conferível.** Barra do circuito = nó da topologia da subrede (com os dois
   terminais de uma chave fechada fundidos numa barra só); `Line` = trecho da subrede; `Transformer` =
   transformador; `Load` = unidade consumidora, e geração distribuída como carga negativa. O `resumo.json`
   sai com essa conferência dentro, e o teste do item a repete por consulta independente ao banco.
3. **Chave fechada vira barra, não `Line ... switch=yes`.** Assim o número de `Line` do circuito é o número
   de trechos, sem elemento fantasma. O preço é não poder abrir a chave dentro do OpenDSS, e esse preço está
   escrito em `NAO_FAZ.md`, que sai dentro da pasta.
4. **O conversor falha alto.** Transformador sem POT_NOM, tensão nominal ausente ou código fora do domínio
   TTEN param a exportação com 422. Escrever 0 kVA ou arbitrar uma tensão daria um circuito que compila e
   diz uma coisa falsa sobre a rede.
5. **Nada é estimado.** Não há catálogo de condutor nem reatância de transformador no pacote de ativos: as
   linhas saem com a impedância padrão do OpenDSS e o código do condutor como comentário, e o transformador
   sai sem `xhl`. As perdas, essas sim, saem de PER_FER e PER_TOT.
6. **Dicionário de tensão completo.** Os 110 códigos do domínio TTEN (0 a 109), conferidos contra o
   `bdgd2opendss` (licença MIT) e contra os 13 códigos do conversor da casa, que continuam com o mesmo valor.
7. **Curva de 864 pontos.** 12 meses × 3 tipos de dia × 24 horas, com o calendário de feriados calculado
   (feriado conta como domingo, como no PRODIST Módulo 7). A conta conserva energia. A forma do dia é plana
   enquanto o acervo não tiver curva típica por classe de consumo, e isso está declarado.
8. **`jusante=true` para o alimentador inteiro.** Uma subrede é de um tier só, e o transformador é a
   fronteira entre média e baixa tensão. Com `jusante=true` o circuito inclui as subredes de tier inferior
   que penduram na pedida — é o alimentador com transformador e carga, que é o que o estudo elétrico quer.

## Consequências

O `opendssdirect.py` entra no `requirements.txt` **só para a suíte**: nada em `app/` o importa, porque o
conversor escreve texto. Ele está ali porque a cláusula do portão é "o circuito compila", e provar isso
exige o motor de verdade. Numa máquina sem ele, o teste pula a compilação com a razão escrita.
