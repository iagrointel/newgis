# ADR 20260908T1400 — continuidade DEC/FEC ligada à rede pela chave CONJ

Item `L4-10-continuidade-dec-fec`. Estado: aceita.

## Contexto

A ANEEL apura os indicadores COLETIVOS de continuidade (DEC, em horas, e FEC, em número de interrupções)
por CONJUNTO DE UNIDADES CONSUMIDORAS, e publica os limites por conjunto e por ano. O conjunto é um recorte
da concessão: não é um alimentador e não é um transformador. A rede que a plataforma importa da BDGD, por
sua vez, traz o campo `CONJ` nas camadas de transformador, de unidade consumidora e de trecho de média
tensão. Não existe indicador de continuidade por alimentador publicado por ninguém.

## Decisões

1. **A junção é por `CONJ`, e o conjunto é a unidade de verdade.** `plat.rede_continuidade` guarda o
   indicador como o arquivo o publica: por conjunto, indicador, ano e mês. A soma do ano é feita na
   leitura, não na carga — assim a base continua conferível contra o arquivo linha a linha.
2. **O alimentador recebe o número do conjunto ponderado por unidade consumidora**, e a resposta diz que
   foi isso que se fez (`metodo`), quantas unidades entraram (`uc_com_dado`) e quantas ficaram de fora
   (`uc_sem_dado`). Alimentador não tem indicador próprio; inventar um seria pior que não ter.
3. **Ausência não vira zero.** Conjunto que a rede declara e o arquivo da ANEEL não publica aparece na
   ficha com valor nulo e situação "sem dado". Zero seria a melhor continuidade possível — o oposto do que
   o dado diz. É a refutação exigida pelo item, e ela tem teste próprio.
4. **Vocabulário travado em teste.** A comparação com o limite produz exatamente quatro frases: "dentro do
   limite", "acima do limite regulatório", "sem limite publicado" e "sem dado". A palavra de acusação não
   aparece em nenhum arquivo do item, e um teste varre o código, a página e a tradução para garantir. Quem
   decide o que é infração e qual a consequência é o processo da agência, não esta leitura.
5. **Nenhum limite escrito no código.** Os limites são os estabelecidos na forma do PRODIST Módulo 8,
   aprovado pela Resolução Normativa ANEEL 956/2021 e seus anexos; os valores vêm do arquivo de limites
   publicado pela própria agência no portal de dados abertos (acesso em 08/09/2026), e cada linha guarda em
   `fonte_id` de qual arquivo veio, com o resumo criptográfico do arquivo.
6. **DIC e FIC são outro dado e são declarados como tal.** Eles são INDIVIDUAIS (por unidade consumidora),
   vêm da própria BDGD (camada de baixa tensão) e não do arquivo de continuidade coletiva. A média por
   transformador é sobre as unidades que trazem o dado, e `n_uc` ao lado de `n_uc_com_dic` diz quanto da
   carteira entrou na conta. Unidade sem nenhum campo de DIC dá NULL, nunca zero.
7. **A compensação paga NÃO entra neste item.** O conjunto de dados de compensação da agência usa outro
   vocabulário de indicador — 96 códigos das famílias PGU* (valor pago) e QTU* (quantidade de unidades
   compensadas) — e nenhum deles é DEC ou FEC. Medido em 08/09/2026 no arquivo de 9.614.399 linhas: zero
   linhas com indicador DEC ou FEC. Ler aquele arquivo com o filtro deste módulo devolveria sempre zero e
   daria a impressão de que a compensação está importada. A coluna `origem` fica na tabela para que ela
   entre depois sem migração nova, mas a leitura é sua própria tarefa.
8. **O job não baixa nada** (D21, disco): a pasta de origem é um ativo local e o caminho só pode apontar
   para dentro de `PLAT_ANEEL_CONTINUIDADE_RAIZ`. Sem a variável, a importação fica desligada e diz isso.
9. **A configuração é verificada DEPOIS da rede.** Quem não enxerga a rede recebe 404 e não descobre se
   esta instalação tem o dado aberto em disco.

## Consequência

O painel `/redes/continuidade` desenha a série 2020-2025 por conjunto com o limite ao lado, e a tabela por
alimentador logo abaixo. O que não se pode responder com este item, e está dito no produto: o indicador por
alimentador medido (não existe), a compensação paga (decisão 7) e as interrupções individuais com causa e
data (o arquivo de ocorrências da agência é outro conjunto de dados, de 317 MB comprimidos, e não foi
importado).
