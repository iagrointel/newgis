# Agregação célula → feição e prova de equivalência com o motor logístico de referência

Data: 07/09/2026 · Item: L3-01-j-equivalencia-motor-logistico · Estado: aceita

## Contexto

A casa já opera um motor multicritério logístico, de outro projeto, com 19 fatores disponíveis sobre uma
grade de 73.115 células de 250 m e 4.346 feições de imóvel. A pergunta deste item é se o motor genérico
desta plataforma — modelo declarativo, extratores, transformações e combinador — reproduz aquele motor
quando recebe os mesmos valores. Reproduzir é a condição para poder substituí-lo sem discutir número.

## Decisões

1. **A passagem célula → feição vira módulo próprio e puro** (`app/amc/agregacao.py`), não um trecho de
   SQL dentro de um pipeline. A regra: cada fator da feição é a média das células ponderada pela área de
   interseção, calculada só sobre as células não vetadas e só sobre as células em que aquele fator tem
   dado; a fração vetada é a área vetada sobre a área intersectada total; o motivo que a feição carrega é
   o da maior área vetada. O denominador ser "a área COM DADO daquele fator", e não a área total, é o
   ponto que faz falta de dado não virar nota baixa.
2. **Arredondar é decisão de armazenamento, não da conta.** O módulo devolve ponto flutuante por padrão.
   Quando se pede inteiro, o desempate é meio para longe do zero, como o `round` do Postgres — o `np.round`
   usa meio para o par e discorda em exatamente 1 ponto nos empates, que é a divergência que apareceria
   contra qualquer base já materializada.
3. **O motor de referência é oráculo, e só leitura.** Nenhuma linha é escrita no schema dele. O nome desse
   schema NÃO fica escrito neste repositório, que é público e cujo schema carrega o nome de um cliente:
   vem da variável de ambiente `PLAT_MOTOR_REFERENCIA_ESQUEMA`. Sem a variável, os testes de equivalência
   são pulados dizendo essa razão em voz alta, em vez de passar sem provar nada.
4. **O oráculo é recalculado em SQL, não em numpy.** A comparação vale mais quando os dois lados não
   compartilham implementação: a favorabilidade de referência é recomposta com aritmética `numeric` do
   Postgres a partir dos mesmos fatores, e comparada com o resultado do combinador em `float64`.
5. **O modelo dos 19 fatores fica em arquivo versionado** (`docs/modelos/motor_logistico_referencia.json`),
   validado pelo esquema `amc_modelo.v1`. Oito fatores trazem a transformação do valor BRUTO; os outros
   onze declaram a identidade sobre um valor que já chega em escala de favorabilidade, porque no motor de
   referência a regra deles compõe mais de uma variável antes de virar nota — e cada um diz isso no campo
   `nao_sustenta`, em vez de fingir que a composição foi reproduzida.

## Consequência que limita o alcance da prova

Dos 19 fatores, o motor de referência só deriva **dez** da grade (decl, zon, gru, rod, disp, ener, agua,
restr, press, dens). Os outros nove ele calcula direto na feição: sete vêm de uma tabela por imóvel, um
(`varzea`) da fração de inundação medida no próprio imóvel e um (`mine`) de um veredito por imóvel. A
equivalência da agregação, portanto, está provada nos dez — nos outros nove ela não se aplica, porque não
foi agregação que os produziu. Isso está medido, não suposto: a nota da feição desses fatores é idêntica à
da fonte por imóvel em 4.346 de 4.346 casos.
