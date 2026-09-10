# Critérios sobre a própria feição no motor multicritério (item L3-06-criterios-de-feicao)

Data: 2026-09-08 · Estado: aceito · Linha: L3 (motor multicritério)

## Contexto

O motor multicritério nasceu sobre GRADE: cada unidade de análise é uma célula, e o fator é o que a célula
mediu. Boa parte do trabalho do usuário, porém, não é sobre células — é sobre feições que ele já tem: um
imóvel, uma loja, um lote. Nessa unidade a pergunta muda de forma: deixa de ser "o que a grade mediu aqui" e
passa a ser uma pergunta feita à feição, no molde da análise de adequação de um Business Analyst.

## Decisão

1. **Quatro perguntas, não um tipo genérico.** `atributo` (número que a feição já carrega), `contagem_raio`
   (pontos de outra camada a até `raio_m`), `contagem_dentro` (pontos dentro da feição) e
   `distancia_mais_proxima` (metros ao ponto mais próximo). Quem mede é `app/amc/vetorial.py`, o MESMO
   extrator que a grade usa — não existe um segundo motor de medição.

2. **Influência é o sentido da preferência, declarado pelo usuário**: `positiva`, `inversa`, `ideal`. As três
   viram um dicionário de transformação de `app/amc/transformacoes.py` (`linear` crescente, `linear`
   decrescente, `linear_simetrica`). Nenhuma curva nova foi escrita para este item.

3. **`ideal` é simétrico por definição.** A queda usa um `alcance` único para os dois lados do alvo. Quando o
   alvo não está no meio de [`minimo`, `maximo`], o alcance adotado é o do lado mais longo: a nota chega a zero
   no extremo mais distante e fica acima de zero no mais próximo. Quem quer zero nas duas pontas declara um alvo
   centrado ou um `alcance` explícito. A escolha vai na ficha do critério (`limites_derivados`), nunca escondida.

4. **Filtro de inclusão não é veto.** `faixa_inclusao` tira a feição da comparação com o estado `filtrada`, sem
   posição no ranque e sem nota; veto (decisão A6) continua sendo o que zera a nota de quem PERMANECE na
   comparação. Valor ausente nunca filtra: falta de dado não é "fora da faixa". As duas coisas juntas na mesma
   coluna seriam a mesma armadilha do `coalesce(fator, 0)` que o motor já recusa.

5. **Correlação entre critérios é par a par, sobre as feições em que os dois têm dado**, e sobre a
   favorabilidade (escala comum 0-100). Par com menos de três linhas em comum, ou com um dos lados constante,
   devolve nulo — devolver 0 nesse caso seria inventar informação.

6. **Sem estado e sem tabela própria.** A rota recebe as feições e as camadas de apoio no corpo e devolve o
   resultado, no mesmo molde de `/api/amc/similaridade`. Não há linha de inquilino a ler ou gravar, logo não há
   RLS a aplicar aqui.

7. **Teto síncrono de 5.000 feições, e o que acontece acima dele.** Acima do teto a API recusa com
   `acima_do_sincrono` e manda para o caminho de LOTE que já existe: gravar um conjunto de unidades e rodar
   `POST /api/amc/execucoes`, que é job. **Não** foi criado um job próprio para esta rota: `plat.amc_unidade`
   guarda geometria e área, não os atributos da feição, e o critério de `atributo` — que é o primeiro dos
   quatro — depende justamente desses atributos. Um job "de critérios de feição" exigiria uma tabela nova de
   atributos por unidade; enquanto ela não existir, prometer o job seria promessa vazia.

## Consequências

- Um modelo com quatro critérios sobre 1.000 feições roda em ~130 ms de máquina, o que cabe numa requisição.
- A contagem em raio tem uma segunda opinião permanente: o teste de API refaz a conta com `ST_DWithin` do
  PostGIS sobre as mesmas feições e os mesmos pontos, e as duas têm de bater feição a feição.
- Quem quiser lote acima de 5.000 tem um caminho, não um erro seco — mas é um caminho DIFERENTE, com conjunto
  de unidades gravado, e isso está dito na mensagem da recusa.
