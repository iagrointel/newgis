# Conectores pandapower e MATPOWER: um modelo, três línguas

Data: 2026-09-08. Item `L4-05-c-pandapower-e-matpower`. Estado: aceito.

## Contexto

O item L4-05-a já exporta a subrede para OpenDSS. Este item pede mais dois formatos de rede
EQUILIBRADA (pandapower e MATPOWER) e a importação de um caso MATPOWER público.

## Decisões

1. **Um modelo em memória, três formatos.** Os conectores consomem o dicionário que
   `opendss.montar_da_subrede` devolve; não há segunda leitura do banco nem segunda regra de conversão.
   A consequência que interessa: comparar a saída pandapower com a saída OpenDSS compara o MESMO
   modelo escrito em duas línguas, o que torna a conferência cruzada uma medida do escritor, não uma
   coincidência de dois pipelines diferentes. Custo: uma mudança na leitura muda os três formatos ao
   mesmo tempo — é o que se quer.

2. **A plataforma não importa pandapower em tempo de execução.** O arquivo do pandapower é JSON, e o
   `.m` é texto; os dois são escritos com a biblioteca padrão. `pandapower` entra em `requirements.txt`
   com a mesma justificativa do `opendssdirect.py`: SÓ A SUÍTE importa, para provar que o arquivo é
   lido pelo motor de verdade e que o fluxo converge. Nada em `app/` o importa. A alternativa —
   montar o `net` chamando `pandapower.create_*` — poria pandas, scipy e o próprio pandapower no
   caminho crítico de uma rota de leitura, por nenhum ganho.

3. **Impedância de referência escrita, não implícita.** O pacote de ativos não tem catálogo de
   condutor. O OpenDSS resolve isso em silêncio (o objeto `Line` sem impedância recebe o padrão do
   motor); o pandapower não roda sem `r`/`x`/`c`. Em vez de inventar um condutor, os conectores
   escrevem os MESMOS valores padrão do OpenDSS, nomeados em
   `pandapower_rede.IMPEDANCIA_REFERENCIA` e repetidos no `NAO_FAZ.md` de toda exportação. Assim os
   três arquivos descrevem a mesma rede elétrica e o que é suposição está escrito.

4. **O caso MATPOWER vai para o grafo de negócio, não para as camadas de feição.** O caseformat não
   tem coordenada nenhuma. `plat.rede_feicao_ponto.geom` é NOT NULL — cabê-lo ali exigiria escrever
   (0, 0), que é uma coordenada real no golfo da Guiné e faria a barra aparecer no mapa como se
   tivesse sido medida. `plat.rede_no`/`rede_aresta` (item L4-01-modelo-rede) têm geometria OPCIONAL e
   é sobre elas que o traçado de menor caminho corre. O pacote novo `transmissao-matpower` declara os
   dois grupos com geometria `sem_geometria`, para que o catálogo diga a mesma coisa que a tabela.

5. **Pacote de ativos próprio para transmissão.** Reusar o `eletrica-br` (vocabulário da BDGD, de
   distribuição) faria um ramo de 345 kV virar "trecho de média tensão". O pacote novo tem 2 grupos,
   6 tipos, 21 atributos e 8 regras — o que o caseformat 2 declara, e nada além. O que a matriz `gen`
   traz entra como atributo da barra: criar um objeto "gerador" que nenhuma aresta liga seria
   estrutura vazia.

6. **Importação síncrona, sem job.** O `case30` público tem 30 barras e 41 ramos, e o teto da rota é
   4 MiB de texto de matriz. Enfileirar job para isso seria maquinaria sem trabalho. A leitura e a
   gravação vão para o threadpool, como no importador de pacote, para não segurar o laço de eventos.

## Consequências

* O `comprimento_m` dos ramos importados fica NULO (o caseformat não traz comprimento). O traçado da
  casa trata isso como custo zero e CONTA quantos ramos entraram assim (`ramais_sem_custo`), então um
  caminho barato demais nunca passa por medição.
* Se a versão pinada do pandapower mudar o esquema das tabelas do `net`, o teste do item reprova — que
  é o comportamento desejado, já que o formato está escrito à mão em `pandapower_rede._TABELAS`.
