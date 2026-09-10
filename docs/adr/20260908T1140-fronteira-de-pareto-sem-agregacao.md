# Fronteira de Pareto: análise sem agregação (item L3-08-pareto)

Data: 08/09/2026. Estado: aceito. Par: `laco/decomposicao/L3L6_CONCEITO.md` (decisões A1 a A6);
ADR `20260907T1013-combinador-amc.md` (L3-01-e, a resposta que vem DEPOIS da escolha de peso).

## Contexto

O combinador responde "qual unidade é a melhor" a partir de pesos que o usuário escolhe. A pergunta
anterior — quais unidades sequer podem ser as melhores, para QUALQUER escolha de peso — não depende de
peso nenhum: são as unidades não dominadas. O item pede essa análise com 2 a 4 objetivos, fronteiras de
2ª e 3ª ordem, gráfico ligado ao mapa e a fronteira exportável como camada.

## Decisão

1. **Módulo puro + duas rotas de leitura.** A conta vive em `app/amc/pareto.py` (numpy, sem banco, sem
   relógio), como o combinador. `POST /api/amc/pareto` devolve a ordem por unidade; `POST
   /api/amc/pareto/camada` devolve as ordens pedidas como GeoJSON. As duas usam POST só porque a lista
   de objetivos não cabe em query string; não escrevem nada e por isso não registram evento de domínio
   (entrada com lista vazia em `tests/api/eventos_esperados.py`, com o motivo ao lado).
2. **A fonte de unidades é a execução do motor de grades aninhadas** (`plat.escala_*`, item
   L3-19-multiescala). É o único conjunto de unidades com id, geometria, valor por fator e RLS por
   inquilino que já está em master. Nada no módulo nem nas rotas depende do formato da grade além de
   "uma unidade tem id, geometria e um valor por fator"; quando o conjunto de unidades genérico
   (L3-01-b) entrar, ele é a segunda fonte, sem mudar a conta.
3. **Escopo de token reusado: `multiescala:usar`.** Um token que não pode ler a execução também não
   pode analisá-la; um verbo novo no vocabulário fechado de `app/auth/escopos.py` não compraria
   isolamento nenhum a mais.
4. **Ausência de dado tira a unidade da ordenação.** Unidade com qualquer objetivo `NULL` sai com ordem
   0 e motivo declarado. Tratar ausência como zero colocaria a unidade sem dado na fronteira quando o
   objetivo é de minimização — o erro clássico desta análise. Célula sem linha de fator na execução
   entra como `NULL`, nunca como zero.
5. **"Camada" aqui é GeoJSON, não item do catálogo.** Publicar o resultado como item catalogado é o
   item L3-13-resultado-como-camada, que ainda não existe; entregar meia catalogação agora criaria um
   segundo caminho para o mesmo objeto. O GeoJSON é o que o mapa desenha e o que o usuário baixa, e traz
   em `metadados` os objetivos, as direções, a contagem por ordem e o aviso dos pesos — o método viaja
   junto com o dado.
6. **Empate não é dominância.** Duas unidades com valores idênticos ficam na mesma ordem. É o que faz a
   refutação do item passar: com dois objetivos iguais, a fronteira é a unidade de valor máximo E todos
   os seus empates, não uma delas escolhida por desempate arbitrário.

## Custo e alternativas descartadas

- **Ordenação rápida (Kung) em vez do laço O(n²).** A peneira ordena em ordem lexicográfica decrescente
  e compara cada candidata só com as que já entraram na fronteira; isso é exato porque, se F domina C, F
  vem antes de C nessa ordem, e a dominância é transitiva. O laço ingênuo O(n²) não foi jogado fora: ele
  é a REFERÊNCIA do teste, escrito do zero em `tests/unit/test_amc_pareto.py`, conferido em 2.000
  unidades com 2, 3 e 4 objetivos, com e sem ausência de dado.
- **Escova (brushing) calculada no servidor.** Descartada: a seleção é interativa e o dado já está no
  navegador. A parte pura da tela (`web/js/amc/pareto.js`) é testada em node, como o combinador.
- **Teto de unidades.** `PARETO_UNIDADES_MAX = 50.000` (contra 250.000 células do motor de grades):
  gerar a grade é barato, devolvê-la com uma linha por unidade não é. Acima do teto a rota recusa com o
  número, em vez de a máquina engasgar.

## Consequências

- **O teto de 50.000 unidades é um teto de tamanho, não de conforto.** Medido nesta máquina, ordenar
  50.000 unidades × 4 objetivos em 3 ordens levou **6.836 ms** com carga de 1 minuto de 5,51 e 5,81 GB
  livres (`tests/medidas/L3-08-pareto.json`). Serve como teto; não serve como interação. O uso
  interativo da tela é da ordem de milhares de unidades, e uma análise acima disso deve virar job
  (L0-05) em vez de resposta síncrona — decisão que fica registrada aqui e não foi implementada nesta
  fatia, porque o item não a pede.
- L3-13 continua responsável por transformar o resultado em item do catálogo; esta entrega não cria
  tabela nem migração nenhuma.
- L3-01-b (conjunto de unidades genérico) entra como segunda fonte das mesmas rotas.
- A tela `/amc/pareto` é a primeira do motor multicritério; a próxima (L3-01-g, tela "Motor") reusa o
  gráfico e o mecanismo de realce daqui.
