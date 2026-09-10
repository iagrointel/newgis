# Fluxo de potência do alimentador: motor OpenDSS em processo próprio, resultado no ponto crítico

Item `L4-07-fluxo-de-potencia`. Data: setembro de 2026. Estado: aceito.

## Contexto

A plataforma já converte a subrede para OpenDSS, pandapower e MATPOWER a partir de um único modelo em
memória (itens L4-05-a e L4-05-c) e já calcula curto-circuito sobre esse mesmo modelo (L4-27). Faltava
resolver o FLUXO DE POTÊNCIA: tensão por barra e fase, corrente e carregamento por trecho, carregamento
por transformador e perda por segmento, no alimentador inteiro, ao longo do ano.

O ArcGIS Utility Network não faz isso. Esta é uma capacidade ALÉM da paridade, e a linha de sempre vale
para tudo o que sai daqui: **triagem, sinal, não prova.**

## Decisões

**1. O motor é o OpenDSS, pela biblioteca `opendssdirect.py` já fixada no `requirements.txt`.** É o motor
que a casa já usava, é trifásico desequilibrado e é o que a ANEEL adota para perdas técnicas no Módulo 7
do PRODIST. Não se escreveu solver próprio e não se trocou por pandapower (que é equilibrado).

**2. O motor roda em PROCESSO FILHO, e isso não é preferência de arquitetura.** Medido em 08/09/2026: o
mesmo alimentador passa quando o OpenDSS é chamado da thread principal e DERRUBA O INTERPRETADOR INTEIRO,
com falha de segmentação, quando é chamado de qualquer outra thread deste processo — que é exatamente o
que uma rota faz, porque o servidor manda trabalho síncrono para um conjunto de threads. Não adiantou
pilha de 64 MB nem trocar a ordem de importação: é biblioteca em Pascal com estado global, num processo
que também carrega GDAL. E não há como capturar a falha: o processo simplesmente some, levando junto a
API ou o worker e todo trabalho em curso.

`resolver` escreve o modelo na entrada padrão de `python -m app.rede_utilidades.fluxo_potencia` e lê o
resultado em JSON. O que se ganha, além de não cair: o pico de memória sai medido no filho (é o número
que o portão do item pede), o diretório de trabalho do processo servidor nunca é mexido (o `Compile` do
OpenDSS troca o diretório de trabalho DO PROCESSO) e dois alimentadores ao mesmo tempo não disputam o
estado global do motor.

**3. Grava-se o estado por elemento NO PONTO CRÍTICO, não em cada um dos 864 pontos.** A varredura anual
tem 24 horas x 3 tipos de dia x 12 meses. Guardar cada elemento em cada ponto daria, num alimentador de
5 mil barras, mais de 4 milhões de linhas por alimentador, e a máquina está com o disco cheio (D21). O
que fica gravado é: o percurso inteiro em grandezas de CIRCUITO (convergência ponto a ponto, perda,
tensão extrema, carga) no resumo da execução, e o estado por elemento no ponto de maior carga do ano —
onde a tensão é mínima e o carregamento máximo. O ponto está identificado (mês, tipo de dia, hora), e
quem quer outro pede `modo=hora`.

**4. Nenhuma leitura devolve número sem o estado de convergência ao lado.** `convergiu` é NOT NULL na
tabela de execução; a tabela, a camada e a resposta do POST trazem `convergencia` junto; a tela escreve
a tarja antes de desenhar qualquer camada e não desenha camada de alimentador que não fechou. E
`agregar` EXCLUI da soma o alimentador que não convergiu, nomeando-o em
`alimentadores_fora_por_nao_convergencia`. Resultado de alimentador que não convergiu é uma leitura do
solver parando, não um estado da rede.

**5. Parâmetro desconhecido é recusado, nunca ignorado.** Quem escreveu `fator_carga` em vez de
`fator_de_carga` tem de saber que o número que voltou não é o que pediu. O modelo de carga ZIP exige os
7 coeficientes declarados: a casa não tem coeficiente medido por classe de consumo, e inventar um
mudaria o resultado inteiro em silêncio.

**6. Carregamento de trecho é sobre uma corrente nominal DECLARADA no pedido.** A BDGD não traz
ampacidade de condutor. Sem esse número não existe "carregamento" nenhum, e ele sai gravado ao lado de
todo carregamento. O mesmo vale para a impedância, que é a padrão do OpenDSS.

**7. Barra com tensão fora de 0,5 a 1,5 por unidade é CONTADA e avisada, não corrigida.** Medido na
cooperativa de teste: onde um trecho de média e um de baixa se encostam sem transformador entre eles, a
propagação de tensão de base atravessa o nó e a barra de baixa recebe base de média — sai com 0,045 pu, e
o transformador ligado ali "perde" quase nada de ferro, porque a perda a vazio cai com o quadrado da
tensão. Corrigir a propagação é do exportador (L4-05-a). Aqui o modelo não mente sobre isso: conta e avisa.

## O que ficou de fora, e por quê

- **Job remoto no servidor com GPU por ssh.** O executor `gpu` existe como declaração em
  `app/jobs/registro.py`, mas o despacho remoto não está implementado na fila — é item da linha de jobs.
  O portão do item aceita "worker desta máquina se a RAM permitir (pico medido)", e o pico está medido.
- **Regulador de tensão, banco de capacitor e manobra de chave** não entram no circuito, porque o
  exportador não os converte (limitação 6 do `NAO_FAZ.md` dele).
- **Estado por elemento fora do ponto crítico**, pela razão de disco da decisão 3.
