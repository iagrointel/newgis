# Expressões no navegador: perfis de uso e geometria esférica (item L5-11-expressoes-no-navegador)

Data: 08/09/2026. Estado: aceito. Par: `docs/EXPRESSAO.md` (seções 5 e 12), ADR do L2-10-d
(regras de atributo), `laco/decomposicao/L2_CONCEITO.md` C6 (linguagem de expressão própria com
dois avaliadores que têm de concordar).

## Contexto

O núcleo da linguagem já existia com dois avaliadores — `app/expressao/avaliador_py.py` no
servidor e `web/js/expressao/avaliador.js` no navegador — comparados vetor a vetor. Faltavam três
coisas para a linguagem ser usável nas telas: um jeito de a expressão enxergar a FEIÇÃO (atributos
e geometria), as funções de geometria que a hipótese do item nomeia (área, comprimento, distância,
dentro) e o contrato de cada lugar onde a expressão é usada (popup, rótulo, cálculo de formulário,
visibilidade, restrição, indicador de painel, título dinâmico).

## Decisão

1. **Perfil é uma camada fina por cima do avaliador, não um avaliador novo.**
   `app/expressao/perfis.py` e `web/js/expressao/perfis.js` só fazem três coisas: montam o contexto
   a partir da feição, escolhem o orçamento (50 ms no navegador, 500 ms no servidor) e conferem o
   TIPO do valor devolvido. A semântica da linguagem é a mesma nos sete perfis — é isso que permite
   a cláusula do portão ("a mesma expressão no popup e no cálculo de formulário dá o mesmo valor")
   ser uma igualdade de verdade e não uma coincidência.
2. **A feição entra como dado, não como objeto.** `$feicao` é o dicionário
   `{"atributos": ..., "geometria": ...}`, `$geometria` é a geometria e cada atributo com nome de
   identificador vira `$nome`. Nada de `getattr`, nada de ligação com o modelo do banco: o
   avaliador continua vendo só uma lista branca de campos, o mesmo contrato que ele já tinha.
   Atributo com espaço ou acento não vira `$nome` — alcança-se por `Atributo($feicao, '<nome>')` —
   e um atributo chamado `feicao` ou `geometria` não sombreia os reservados.
3. **Geometria é GeoJSON com as chaves do próprio padrão** (`type`/`coordinates`), não um formato
   nosso: é o que já viaja entre a API, o MapLibre e o navegador, e reescrever os nomes em
   português obrigaria a converter nas duas pontas sem ganho nenhum.
4. **O modelo da Terra é a esfera, e o resultado é arredondado a 6 casas decimais.** Não há PostGIS
   no navegador e não há como um cálculo de servidor e um de cliente baterem se cada um usar a
   biblioteca de geometria da sua língua. Então: mesma fórmula fechada escrita duas vezes
   (Chamberlain & Duquette para área, haversine para comprimento e distância, cruzamento de raio
   par-ímpar para `Dentro`), esfera de raio autálico 6.371.008,8 m, e arredondamento a 6 casas
   porque `sin`/`cos`/`asin` do Python e do V8 podem divergir no último bit. O preço está escrito
   no manual e no `docs/EXPRESSAO.md`: erro de modelo de até 0,5 % contra o elipsoide, serve para
   ordem de grandeza e comparação, nunca para medição legal de área.
5. **A seção do manual é gerada do código** (`docs/gerar_manual_expressao.py`, mesmo padrão de
   `docs/gerar_limites.py`), com um exemplo por função vindo da própria `TABELA_FUNCOES`. Manual
   escrito à mão envelhece em silêncio; este reprova no teste no dia em que o código muda.

## Consequências

- Quem for ligar popup, rótulo ou formulário à linguagem chama `avaliar_perfil`/`avaliarPerfil` e
  não monta contexto por conta própria — se montar, perde a lista branca e o orçamento.
- Acrescentar função nova exige mexer nos DOIS avaliadores e no `docs/EXPRESSAO.md` no mesmo
  commit: `test_expressao_doc_sincronizada.py` reprova qualquer um dos três sozinho.
- Geometria com muitos vértices consome o orçamento de passos (cada posição custa um passo) e o
  teto de coleção (1.024 posições por anel): polígono grande tem de ser simplificado antes.
- Nenhuma tela chama isto ainda. A ligação com popup, rótulo e formulário é dos itens de tela; até
  lá o que existe é a biblioteca, provada nos dois runtimes.

## Alternativas descartadas

- **Um avaliador só, no servidor, com o navegador pedindo por HTTP**: mata o popup (uma ida ao
  servidor por feição clicada) e o rótulo (uma por quadro), e o item se chama "no navegador".
- **Turf.js no cliente + PostGIS no servidor**: dois modelos de geometria diferentes, dois erros
  numéricos diferentes, nenhuma chance de o mesmo número sair dos dois lados — exatamente o que o
  portão proíbe. Além de dependência nova, que a escada do Ponytail manda evitar.
- **Elipsoide (fórmula de Vincenty/Karney)**: mais exato e mais caro, com convergência iterativa
  que é justamente onde as duas línguas divergem. Sem ganho para triagem visual, que é o uso.
- **Tolerância de borda em `Dentro`**: qualquer tolerância vira um número arbitrário a defender.
  A regra publicada é exata: borda do anel externo conta como dentro, borda de buraco conta como
  fora.
