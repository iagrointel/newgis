# Montante e jusante vêm do controlador de subrede, não do desenho da linha

Item `L4-02-b-montante-jusante`. Estado: aceito.

## Contexto

A plataforma já tinha dois traçados de sentido: `tipo=montante|jusante` do item L4-18, que anda pela direção
declarada no atributo `direcao_fluxo` de cada trecho. Isso resolve a rede simples (hidrografia, por exemplo),
onde o operador tem esse campo. Numa rede de utilidades importada da BDGD ninguém preenche esse campo: o que
existe é o alimentador e o transformador, isto é, o CONTROLADOR DE SUBREDE do item L4-04-a.

## Decisão

O sentido, numa rede com controlador de subrede em tier hierárquico, vem da distância ao controlador:

* raízes = controladores de papel `fonte` do tier hierárquico de MENOR `ordem` que tenha controlador com nó
  na topologia. Numa rede elétrica marcada pela importação, isso são os alimentadores; partir também dos
  transformadores (tier de baixa tensão, ordem maior) quebraria o montante da baixa tensão no próprio
  transformador, que é justamente o caminho que se quer percorrer;
* a árvore de caminhos mínimos sai de `public.pgr_drivingDistance(..., directed := false, equicost := true)`
  sobre o MESMO grafo de `tracado.py` (arestas reais + arestas virtuais de dispositivo, chave aberta cortando,
  barreira do chamador removida). `equicost` é o que atribui cada nó ao controlador mais próximo quando há
  vários; `pred` dá o pai de cada nó;
* jusante de um ponto = a subárvore dele; montante = a cadeia de pais até a raiz;
* a fronteira de transformação NÃO corta aqui (ao contrário de `tipo=subrede`): atravessar o transformador é
  o que permite ao montante de uma unidade consumidora chegar ao alimentador.

O campo `origem_direcao` (`auto`/`controlador`/`atributo`) entra no pedido e SEMPRE sai na resposta.
`auto` usa o controlador quando ele existe e o atributo quando não existe.

## O que o traçado se recusa a responder

* tier PARTICIONADO (malha): a hierarquia não define sentido. Se algum trecho declara `direcao_fluxo`, o
  pedido é atendido por atributo; se nenhum declara, a resposta é `direcao='indeterminado'` com o motivo.
* LAÇO: se o grafo alcançável tem corda (aresta fora da árvore de caminhos mínimos), há mais de um caminho
  até o controlador, e o que está acima de quem depende do caminho. Quando o laço toca o resultado pedido, a
  resposta é `direcao='indeterminado'` com `nos_do_laco`.
* ponto que nenhum controlador alcança: `direcao='indeterminado'`, motivo `ponto_sem_controlador`.

## Alternativas descartadas

* Tratar direção indefinida como bidirecional: devolveria, no montante, o que está a jusante. Silêncio é pior
  que resultado curto, mas resultado errado é pior que os dois.
* Um segundo motor de traçado para o sentido: o grafo, a resolução de ponto, a barreira e o formato de saída
  são os de `tracado.py`, e continuam sendo — este módulo acrescenta a árvore de caminhos mínimos, nada mais.

## Fronteira honesta

A cláusula do portão que compara o jusante de cada transformador da cooperativa de teste com as unidades
consumidoras que o arquivo liga a ele tem universo VAZIO nesse arquivo: os 26.581 ramais de ligação não têm
geometria, então nenhuma unidade consumidora tem caminho desenhado até o transformador. Medido e gravado em
`tests/medidas/L4-02-b-montante-jusante.json` (`universo_cooperativa`), nunca declarado cumprido.
