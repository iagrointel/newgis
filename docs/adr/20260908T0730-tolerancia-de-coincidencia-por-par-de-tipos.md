# Tolerância de coincidência por par de tipos, não por rede

- Data: 2026-09-08
- Estado: aceita
- Item: L4-01-f-alcance-do-tracado-rede-real

## Contexto

A topologia derivada funde candidatos que coincidem dentro de UMA tolerância, a da rede
(`plat.rede.tolerancia_m`, padrão 0,05 m). Medido no ativo de referência, isso deixava 34 de 50
transformadores alcançáveis a jusante do controlador de um alimentador.

A causa não é a régua estar apertada demais em geral: é a precisão da coordenada não ser a mesma em toda
camada. A camada de ponto do arquivo guarda a coordenada com 6 casas decimais de grau; a de linha, com 13.
Meia unidade da última casa de 6 decimais vale 5e-7 grau — 0,055 m em latitude e 0,048 m naquela longitude,
até 0,073 m de deslocamento do MESMO ponto físico. Conferido: os 50 transformadores do alimentador medido
têm uma ponta de trecho cuja coordenada, arredondada a 6 casas, é igual à deles.

Subir a tolerância da rede resolveria o alcance e estragaria o sentido: com 1,0 m, os laços da média tensão
do ativo sobem de 584 para 638, porque nessa folga o que funde são pontas de trechos VIZINHOS, e com laço o
traçado a jusante recusa arbitrar direção.

## Decisão

1. A tolerância passa a ser declarada também por PAR DE TIPOS, em `plat.rede_regra.tolerancia_m` (NULL = a
   da rede). É dado do pacote de ativos, não código: o pacote `eletrica-br` declara 0,10 m nos pares que
   envolvem dispositivo de cadastro de ponto, e o par (trecho, trecho) nunca ganha folga.
2. A busca de pares é feita pela MAIOR tolerância em jogo e a distância volta com o par; quem decide a fusão
   é a tolerância daquele par de tipos.
3. A folga extra vale para reencontrar o MESMO ponto, nunca para alcançar um SEGUNDO: por dispositivo,
   havendo candidato dentro da tolerância da rede, só esses valem; não havendo, vale o mais próximo (e o que
   estiver a menos da tolerância da rede dele).
4. O que sobra órfão sai por CLASSE, com contagem, distância e exemplo
   (`GET /api/rede/{id}/topologia/diagnostico`), para que o próximo conserto seja escolhido pela causa.

## Consequências

- O número 0,10 m tem origem lida do arquivo (precisão da coordenada da camada de ponto), não tentativa.
  Outro arquivo com outra precisão declara outro número no seu pacote, sem tocar em código.
- A trava 3 é uma convenção declarada: um dispositivo que esteja de fato entre duas pontas distintas, ambas
  além da tolerância da rede, liga só à mais próxima. Sem ela o produto fabricaria laço.
- Fica de fora desta passagem a QUEBRA DE ARESTA em derivação declarada (dispositivo encostando no meio de
  um trecho). Medido no ativo: 0 de 5.481 transformadores e 5 de 3.046 pontas soltas da média tensão
  inteira estariam nessa condição — a classe existe no diagnóstico, o conserto não se paga aqui.
